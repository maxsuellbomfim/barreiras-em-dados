import type { Metadata } from "next";
import { connection } from "next/server";

import {
  getPublicExpenseReports,
  type PublicExpenseReport,
} from "../../lib/expenses";
import {
  financeResourceLabel,
  getPublicFinanceDocuments,
  mergePublicFinanceDocumentResults,
} from "../../lib/finance-documents";
import {
  formatBrlDecimal,
  getPublicRevenues,
  type PublicRevenue,
} from "../../lib/revenues";
import {
  getPublicMonthlyFinanceClosures,
  type PublicMonthlyFinanceClosure,
} from "../../lib/monthly-finance";
import { monthlyFinanceHref } from "../../lib/monthly-finance-detail.mjs";
import { summarizeAnnualFinances } from "../../lib/annual-finance-summary.mjs";
import ShareLink from "../share-link";
import { getPublicFinanceSignals, type PublicFinanceSignal } from "../../lib/finance-signals";
import { getPublicFinanceCoverage } from "../../lib/finance-coverage";
import {
  getPublicObligationCoverage,
  getPublicObligations,
  type PublicObligation,
} from "../../lib/public-obligations.mjs";
import {
  getPublicNonpayrollWorkforceCoverage,
  getPublicPayrollRegimeBreakdown,
  getPublicPayrollCompensationDistribution,
  getPublicPayrollCoverage,
  getPublicPayrollMonths,
  payrollCompensationMatchesMonth,
  payrollRegimeBreakdownMatchesMonth,
  summarizePublicPayrollYears,
  type PublicPayrollMonth,
} from "../../lib/public-payroll.mjs";
import FinanceNonpayrollWorkforceCoverage from "./finance-nonpayroll-workforce-coverage";
import FinancePayrollHistory from "./finance-payroll-history";
import FinancePayrollRegimeBreakdown from "./finance-payroll-regime-breakdown";
import FinancePayrollCompensation from "./finance-payroll-compensation";
import FinancePayrollSources from "./finance-payroll-sources";
import FinancePayrollYears from "./finance-payroll-years";
import { FinanceAnnualSummary } from "./finance-annual-summary";
import { FinanceSiconfiAnnualTotals } from "./finance-siconfi-annual-totals";
import { getPublicSiconfiAnnualTotals } from "../../lib/siconfi-annual-totals";
import { getPublicSiconfiMonthlyReconciliation } from "../../lib/siconfi-monthly-reconciliation";
import { buildFinanceFamilyCoverage } from "../../lib/finance-family-coverage.mjs";
import FinanceFamilyCoverageMap from "./finance-family-coverage-map";

export const revalidate = 300;

const FINANCE_OVERVIEW_LIMIT = 6;

export const metadata: Metadata = {
  title: "Finanças públicas",
  description:
    "Receitas, despesas e documentos financeiros municipais com fonte verificável.",
  openGraph: {
    title: "Quanto a Prefeitura de Barreiras arrecadou e pagou",
    description:
      "Receitas e despesas mês a mês, com o relatório oficial que comprova cada valor.",
  },
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "data não informada";
  const parsed = new Date(`${value}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function formatCollectedAt(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function sortableDate(value: string | null): number | null {
  if (!value) return null;
  const brazilianDate = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (brazilianDate) {
    const [, day, month, year] = brazilianDate;
    return Date.UTC(Number(year), Number(month) - 1, Number(day));
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

function isFiscalDocument(document: { sourceResource: string }): boolean {
  return document.sourceResource === "rreo" || document.sourceResource === "rgf";
}

function isObligationDocument(document: { sourceResource: string }): boolean {
  return document.sourceResource === "balancetes";
}

function isMunicipalControlDocument(document: { sourceResource: string }): boolean {
  return document.sourceResource === "pdc-contas-anuais";
}

function sortNewest<T extends { revenueDate?: string | null; referenceDate?: string | null; collectedAt: string }>(
  rows: readonly T[],
  dateKey: "revenueDate" | "referenceDate",
): T[] {
  return [...rows].sort((left, right) => {
    const leftDate = sortableDate(left[dateKey] ?? null) ?? sortableDate(left.collectedAt) ?? 0;
    const rightDate = sortableDate(right[dateKey] ?? null) ?? sortableDate(right.collectedAt) ?? 0;
    return rightDate - leftDate;
  });
}

function explainRevenue(revenue: PublicRevenue): string {
  if (revenue.collectionDirection === "adjustment") {
    return `Este registro é um ajuste negativo de ${formatBrlDecimal(revenue.collectedAmount)} no período. O documento oficial o apresenta fora do grupo de deduções; por isso ele é mostrado separadamente e não é tratado como arrecadação bruta.`;
  }
  if (revenue.collectionDirection === "deduction") {
    return `Este registro é uma dedução de ${formatBrlDecimal(revenue.collectedAmount)} no período. Ela aparece com sinal negativo para não ser confundida com arrecadação bruta.`;
  }
  return `Este registro representa ${formatBrlDecimal(revenue.collectedAmount)} arrecadados no período. O acumulado informado no relatório é ${formatBrlDecimal(revenue.accumulatedAmount)}.`;
}

function formatPeriod(report: PublicExpenseReport): string {
  return `${formatDate(report.periodStart)} a ${formatDate(report.periodEnd)}`;
}

function formatMonthTitle(value: string): string {
  const parsed = new Date(`${value}T12:00:00-03:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

function closureStatusLabel(status: PublicMonthlyFinanceClosure["closureStatus"]): string {
  if (status === "operational") return "Fechamento operacional disponível";
  if (status === "needs_review") return "Fechamento aguardando reconciliação";
  return "Fechamento parcial";
}

function financeStatusHeading(closure: PublicMonthlyFinanceClosure | null): string {
  if (!closure) return "Ainda não há um fechamento mensal publicado";
  if (closure.closureStatus === "needs_review") return "O último mês ainda precisa de reconciliação";
  if (closure.closureStatus === "needs_data") return "O último mês tem dados parciais";
  if (!closure.operationalDifferenceAmount) {
    return "O último mês foi fechado, mas a diferença ainda não foi calculada";
  }
  return closure.operationalDifferenceAmount.startsWith("-")
    ? "No último mês, os pagamentos ficaram acima da receita declarada"
    : "No último mês, a receita declarada ficou acima dos pagamentos";
}

function financeStatusDescription(closure: PublicMonthlyFinanceClosure | null): string {
  if (!closure) {
    return "Os pagamentos de cada mês já aparecem na seção Despesas, logo abaixo. O fechamento completo — receita e pagamento do mesmo período lado a lado — é publicado quando os dois relatórios oficiais do mês estiverem reconciliados.";
  }
  if (closure.closureStatus !== "operational") return closure.coverageNote;
  return "Esta é uma diferença operacional calculada por código, não uma conclusão de superávit ou déficit fiscal. Ela não inclui ainda todas as dívidas, restos a pagar e demais obrigações.";
}

function financeStatusPill(closure: PublicMonthlyFinanceClosure | null): string {
  if (!closure) return "Fechamento aguardando dados";
  if (closure.closureStatus === "needs_review") return "Requer reconciliação";
  if (closure.closureStatus === "needs_data") return "Dados parciais";
  if (!closure.operationalDifferenceAmount) return "Diferença indisponível";
  return closure.operationalDifferenceAmount.startsWith("-")
    ? "Diferença operacional negativa"
    : "Diferença operacional positiva";
}

function financeDifferenceClass(value: string | null): string {
  if (!value) return "";
  return value.startsWith("-") ? "finance-negative-value" : "finance-positive-value";
}

function explainClosure(closure: PublicMonthlyFinanceClosure): string {
  if (closure.closureStatus === "operational" && closure.operationalDifferenceAmount) {
    const direction = closure.operationalDifferenceAmount.startsWith("-")
      ? "ficou abaixo"
      : "ficou acima";
    return `A receita total declarada no relatório ${direction} dos pagamentos efetivados em ${formatMonthTitle(closure.periodEnd)}. Esta é uma diferença operacional, não uma conclusão de superávit ou déficit fiscal.`;
  }
  return closure.coverageNote;
}

function signalSeverityLabel(severity: PublicFinanceSignal["severity"]): string {
  if (severity === "high") return "atenção alta";
  if (severity === "medium") return "atenção";
  if (severity === "low") return "reconciliação";
  return "informativo";
}

function formatAmount(value: string | null, unavailable = "não disponível"): string {
  return value === null ? unavailable : formatBrlDecimal(value);
}

export default async function FinancesPage() {
  await connection();
  const [
    expensesResult,
    revenuesResult,
    documentsResult,
    monthlyResult,
    signalsResult,
    coverageResult,
    obligationsResult,
    obligationCoverageResult,
    payrollResult,
    payrollCoverageResult,
    nonpayrollWorkforceCoverageResult,
    siconfiAnnualResult,
    siconfiReconciliationResult,
    rreoDocumentsResult,
    rgfDocumentsResult,
    municipalControlDocumentsResult,
    balanceteDocumentsResult,
    revenueDocumentsResult,
    expenseDocumentsResult,
  ] = await Promise.all([
    getPublicExpenseReports(),
    getPublicRevenues(),
    getPublicFinanceDocuments(),
    getPublicMonthlyFinanceClosures(),
    getPublicFinanceSignals(),
    getPublicFinanceCoverage(),
    getPublicObligations(),
    getPublicObligationCoverage(),
    getPublicPayrollMonths(120),
    getPublicPayrollCoverage(120),
    getPublicNonpayrollWorkforceCoverage(120),
    getPublicSiconfiAnnualTotals(),
    getPublicSiconfiMonthlyReconciliation(),
    getPublicFinanceDocuments("rreo"),
    getPublicFinanceDocuments("rgf"),
    getPublicFinanceDocuments("pdc-contas-anuais"),
    getPublicFinanceDocuments("balancetes"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-receita"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-despesa"),
  ]);
  const expenseReports =
    expensesResult.state === "available" ? expensesResult.reports : [];
  const sortedExpenseReports = [...expenseReports].sort((left, right) =>
    right.periodEnd.localeCompare(left.periodEnd),
  );
  const latestExpenseReport = sortedExpenseReports[0] ?? null;
  const revenues =
    revenuesResult.state === "available" ? revenuesResult.revenues : [];
  const documents = mergePublicFinanceDocumentResults(
    documentsResult,
    rreoDocumentsResult,
    rgfDocumentsResult,
    municipalControlDocumentsResult,
    balanceteDocumentsResult,
    revenueDocumentsResult,
    expenseDocumentsResult,
  );
  const monthlyClosures =
    monthlyResult.state === "available" ? monthlyResult.closures : [];
  const financeSignals = signalsResult.state === "available" ? signalsResult.signals : [];
  const recentFinanceSignals = financeSignals.slice(0, FINANCE_OVERVIEW_LIMIT);
  const publicObligations =
    obligationsResult.state === "available"
      ? obligationsResult.obligations
          .filter((obligation) => obligation.obligationType === "restos_a_pagar_total")
          .sort((left, right) => right.periodEnd.localeCompare(left.periodEnd))
      : [];
  const publicObligationCoverage =
    obligationCoverageResult.state === "available"
      ? obligationCoverageResult.rows
      : [];
  const payrollMonths =
    payrollResult.state === "available" ? payrollResult.months : [];
  const latestPayroll: PublicPayrollMonth | null = payrollMonths[0] ?? null;
  const payrollRegimeResult = latestPayroll
    ? await getPublicPayrollRegimeBreakdown(latestPayroll.referenceMonth)
    : { state: "unavailable" as const };
  const payrollRegimeRows =
    payrollRegimeResult.state === "available" &&
    payrollRegimeBreakdownMatchesMonth(payrollRegimeResult.rows, latestPayroll)
      ? payrollRegimeResult.rows
      : [];
  const payrollCompensationResult = latestPayroll
    ? await getPublicPayrollCompensationDistribution(latestPayroll.referenceMonth)
    : { state: "unavailable" as const };
  const payrollCompensationRows =
    payrollCompensationResult.state === "available" &&
    payrollCompensationMatchesMonth(
      payrollCompensationResult.rows,
      latestPayroll,
    )
      ? payrollCompensationResult.rows
      : [];
  const previousPayrollMonths = payrollMonths.slice(1, FINANCE_OVERVIEW_LIMIT + 1);
  const previousPayrollMonthCount = Math.max(0, payrollMonths.length - 1);
  const payrollYearSummaries = summarizePublicPayrollYears(payrollMonths);
  const payrollCoverageRows =
    payrollCoverageResult.state === "available"
      ? payrollCoverageResult.rows
      : [];
  const nonpayrollWorkforceCoverageRows =
    nonpayrollWorkforceCoverageResult.state === "available"
      ? nonpayrollWorkforceCoverageResult.rows
      : [];
  const payrollCoverageGapCount = payrollCoverageRows.filter(
    (row) => row.coverageStatus !== "published",
  ).length;
  const siconfiAnnualYears =
    siconfiAnnualResult.state === "available"
      ? siconfiAnnualResult.years
      : [];
  const siconfiReconciliationYears =
    siconfiReconciliationResult.state === "available"
      ? siconfiReconciliationResult.years
      : [];
  const obligationCoverageGapCount = publicObligationCoverage.filter(
    (row) => row.coverageStatus !== "published",
  ).length;
  const latestPublicObligation = publicObligations[0] ?? null;
  const publishedObligationMonths =
    publicObligationCoverage.length > 0
      ? publicObligationCoverage.filter((row) => row.coverageStatus === "published")
          .length
      : publicObligations.length;
  const obligationSectionAbsentMonths = publicObligationCoverage.filter(
    (row) => row.coverageStatus === "section_absent",
  ).length;
  const obligationSectionIncompleteMonths = publicObligationCoverage.filter(
    (row) => row.coverageStatus === "section_incomplete",
  ).length;
  const obligationSourceConflictMonths = publicObligationCoverage.filter(
    (row) => row.coverageStatus === "source_conflict",
  ).length;
  const sortedRevenues = sortNewest(revenues, "revenueDate");
  const recentRevenues = sortedRevenues.slice(0, FINANCE_OVERVIEW_LIMIT);
  const recentExpenseReports = sortedExpenseReports.slice(0, FINANCE_OVERVIEW_LIMIT);
  const recentPublicObligations = publicObligations.slice(0, FINANCE_OVERVIEW_LIMIT);
  const sortedDocuments = sortNewest(documents, "referenceDate");
  const fiscalDocuments = sortedDocuments.filter(isFiscalDocument);
  const recentFiscalDocuments = fiscalDocuments.slice(0, FINANCE_OVERVIEW_LIMIT);
  const obligationDocuments = sortedDocuments.filter(isObligationDocument);
  const recentObligationDocuments = obligationDocuments.slice(0, FINANCE_OVERVIEW_LIMIT);
  const municipalControlDocuments = sortedDocuments.filter(isMunicipalControlDocument);
  const operationalDocuments = sortedDocuments.filter(
    (document) =>
      !isFiscalDocument(document) &&
      !isObligationDocument(document) &&
      !isMunicipalControlDocument(document),
  );
  const recentOperationalDocuments = operationalDocuments.slice(0, FINANCE_OVERVIEW_LIMIT);
  const sortedMonthlyClosures = [...monthlyClosures].sort((left, right) =>
    right.periodEnd.localeCompare(left.periodEnd),
  );
  const recentMonthlyClosures = sortedMonthlyClosures.slice(0, FINANCE_OVERVIEW_LIMIT);
  const annualFinanceSummaries = summarizeAnnualFinances(sortedMonthlyClosures);
  const latestRevenue = sortedRevenues[0]?.revenueDate ?? null;
  const latestClosure = sortedMonthlyClosures[0] ?? null;
  const financeFamilies = buildFinanceFamilyCoverage({
    financeRows: coverageResult.state === "available" ? coverageResult.rows : [],
    obligationRows: publicObligationCoverage,
    payrollRows: payrollCoverageRows,
    fiscalDocuments,
    siconfiYears: siconfiAnnualYears,
  });
  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/licitacoes">Compras</a>
            <a href="/representantes">Quem decide</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="finances-title">
        <div className="section-heading">
          <span className="eyebrow">Dinheiro público</span>
          <h1 id="finances-title">Finanças públicas, sem esconder a conta.</h1>
          <p>
            Acompanhe receitas já normalizadas e os documentos oficiais que
            registram arrecadação, despesas, transferências e relatórios fiscais.
            Quando um valor ainda estiver em um PDF, mostramos o documento e
            deixamos explícito que a extração numérica ainda não foi validada.
          </p>
          <ShareLink
            path="/financas"
            message="Quanto a Prefeitura de Barreiras arrecadou e pagou, com o relatório oficial de cada valor:"
          />
        </div>

        <section className="finance-guide" aria-labelledby="finance-guide-title">
          <div className="section-heading compact">
            <span className="eyebrow">Em palavras simples</span>
            <h2 id="finance-guide-title">O que cada número quer dizer</h2>
            <p>
              A Prefeitura registra uma despesa em etapas. Elas não são o mesmo
              dinheiro e não devem ser somadas.
            </p>
          </div>
          <div className="finance-guide-grid">
            <article>
              <strong>Orçamento atualizado</strong>
              <p>O limite de gasto depois dos ajustes do ano. Não significa que esse valor já foi gasto.</p>
            </article>
            <article>
              <strong>Reservado</strong>
              <p>Valor separado para uma contratação ou outra despesa. No relatório, aparece como empenhado.</p>
            </article>
            <article>
              <strong>Conferido</strong>
              <p>Parte que já teve entrega ou serviço verificado. É a etapa liquidada.</p>
            </article>
            <article>
              <strong>Pago</strong>
              <p>Dinheiro que efetivamente saiu do caixa no período informado.</p>
            </article>
          </div>
          <p className="finance-guide-note">
            A leitura principal é “Pago”: ela responde quanto saiu do caixa. Os
            demais números ajudam a acompanhar o caminho da despesa.
          </p>
          <p className="finance-guide-note">
            <strong>Como conferimos:</strong> cada valor precisa apontar para o
            mesmo registro e a mesma URL do PDF oficial. Se esse vínculo não
            puder ser provado, o valor fica fora dos totais até a correção.
            A versão anterior permanece no histórico de auditoria; ausência de
            valor nunca significa arrecadação ou gasto zero.
          </p>
        </section>

        <FinanceFamilyCoverageMap families={financeFamilies} />

        <section className="finance-status-panel" aria-labelledby="finance-coverage-hub-title">
          <div>
            <span className="eyebrow">Cobertura completa</span>
            <h2 id="finance-coverage-hub-title">Confira cada período e cada documento</h2>
            <p>
              A auditoria separa receitas e despesas, folha, restos a pagar,
              documentos mensais, RREO e RGF. Os calendários mostram desde 2021 o
              que foi preservado, o que está em validação e o que não foi localizado.
            </p>
          </div>
          <a className="finance-month-link" href="/financas/cobertura">
            Abrir cobertura completa por período →
          </a>
        </section>

        <FinanceSiconfiAnnualTotals
          years={siconfiAnnualYears}
          reconciliationYears={siconfiReconciliationYears}
        />

        <section className="finance-status-panel" aria-labelledby="finance-status-title">
          <div>
            <span className="eyebrow">Resultado das contas</span>
            <h2 id="finance-status-title">{financeStatusHeading(latestClosure)}</h2>
            <p>{financeStatusDescription(latestClosure)}</p>
          </div>
          <span className="finance-status-pill">{financeStatusPill(latestClosure)}</span>
        </section>

        <section className="finance-at-a-glance" aria-labelledby="finance-glance-title">
          <div className="section-heading compact">
            <span className="eyebrow">Resumo para começar</span>
            <h2 id="finance-glance-title">Quanto entrou, quanto saiu e quanto devemos</h2>
            <p>
              Este painel mostra o último fechamento mensal disponível. “Diferença
              operacional” não é saldo bancário nem dívida: é apenas receita
              declarada menos pagamentos do mesmo período.
            </p>
          </div>
          <div className="finance-at-a-glance-grid">
            <article className="finance-glance-card finance-positive-card">
              <span>Entrou no último mês</span>
              <strong>{formatAmount(latestClosure?.revenueReportAmount ?? null)}</strong>
              <small>{latestClosure ? formatMonthTitle(latestClosure.periodEnd) : "Fechamento ainda não disponível"}</small>
            </article>
            <article className="finance-glance-card finance-negative-card">
              <span>Saiu no último mês</span>
              <strong>{formatAmount(latestClosure?.expensePaidAmount ?? null)}</strong>
              <small>Pagamentos efetivados no período</small>
            </article>
            <article className="finance-glance-card finance-debt-card">
              <span>Dívida registrada</span>
              <strong>
                {obligationDocuments.length > 0
                  ? `${obligationDocuments.length.toLocaleString("pt-BR")} documentos em apuração`
                  : "Fontes em integração"}
              </strong>
              <small>Nenhum total é publicado antes da reconciliação das obrigações.</small>
            </article>
          </div>
        </section>

        <section
          className="finance-payroll-section"
          aria-labelledby="finance-payroll-title"
        >
          <div className="section-heading compact">
            <span className="eyebrow">Folha mensal</span>
            <h2 id="finance-payroll-title">Quanto custa a folha da Prefeitura</h2>
            <p>
              Total consolidado de todos os processamentos oficiais do mês,
              sem publicar nomes, matrículas, contas bancárias ou descontos
              individuais.
            </p>
          </div>
          {latestPayroll ? (
            <>
              <article className="finance-payroll-card">
                <div className="finance-payroll-header">
                  <div>
                    <span className="finance-payroll-kicker">
                      {latestPayroll.publicBodyName}
                    </span>
                    <h3>{formatMonthTitle(latestPayroll.referenceMonth)}</h3>
                    <p>
                      A folha regular informa{" "}
                      <strong>
                        {latestPayroll.employeeCount.toLocaleString("pt-BR")} vínculos
                      </strong>
                      . Um vínculo não representa necessariamente uma pessoa única.
                    </p>
                  </div>
                  <span className="finance-payroll-status">
                    {latestPayroll.documentCount.toLocaleString("pt-BR")} PDF
                    {latestPayroll.documentCount === 1 ? "" : "s"} reconciliado
                    {latestPayroll.documentCount === 1 ? "" : "s"}
                  </span>
                </div>
                <dl className="finance-payroll-values">
                  <div className="finance-payroll-gross">
                    <dt>
                      Proventos brutos do mês
                      <small>Soma dos processamentos oficiais publicados</small>
                    </dt>
                    <dd>{formatBrlDecimal(latestPayroll.grossAmount)}</dd>
                  </div>
                  <div>
                    <dt>
                      Descontos
                      <small>Retenções consolidadas, sem detalhe pessoal</small>
                    </dt>
                    <dd>{formatBrlDecimal(latestPayroll.deductionAmount)}</dd>
                  </div>
                  <div className="finance-payroll-net">
                    <dt>
                      Líquido nos relatórios
                      <small>Bruto menos descontos; não é confirmação bancária</small>
                    </dt>
                    <dd>{formatBrlDecimal(latestPayroll.netAmount)}</dd>
                  </div>
                </dl>
                <div className="finance-payroll-reading">
                  <strong>Como ler este mês</strong>
                  <p>
                    O total reúne {latestPayroll.documentCount.toLocaleString("pt-BR")}{" "}
                    {latestPayroll.documentCount === 1
                      ? "processamento oficial"
                      : "processamentos oficiais"}
                    :{" "}
                    {formatBrlDecimal(latestPayroll.grossAmount)} brutos,{" "}
                    {formatBrlDecimal(latestPayroll.deductionAmount)} em descontos
                    e {formatBrlDecimal(latestPayroll.netAmount)} líquidos. O código
                    conferiu {latestPayroll.subtotalCount.toLocaleString("pt-BR")}{" "}
                    subtotais sem somar os vínculos repetidos no 13º.
                  </p>
                </div>
                <FinancePayrollRegimeBreakdown
                  rows={payrollRegimeRows}
                  grossTotal={latestPayroll.grossAmount}
                />
                <FinancePayrollCompensation rows={payrollCompensationRows} />
                <details className="finance-details">
                  <summary>Conferir cálculo, fonte e documento</summary>
                  <p className="finance-details-note">
                    Regra determinística: proventos brutos − descontos = líquido.
                    O Barreiras 360 não usa IA para calcular esses valores.
                  </p>
                  <FinancePayrollSources documents={latestPayroll.sourceDocuments} />
                  <p className="finance-details-note">
                    Projeção mensal {latestPayroll.parserVersion}. Cada documento
                    mantém hash e data de coleta próprios.
                  </p>
                </details>
              </article>

              <FinancePayrollYears summaries={payrollYearSummaries} />
              <FinancePayrollHistory
                months={previousPayrollMonths}
                totalMonths={previousPayrollMonthCount}
              />
              {payrollCoverageGapCount > 0 ? (
                <aside
                  className="finance-status-panel"
                  aria-label="Cobertura incompleta da folha"
                >
                  <div>
                    <strong>
                      {payrollCoverageGapCount.toLocaleString("pt-BR")} competências sem total publicado
                    </strong>
                    <p>
                      Isso não significa gasto zero. O calendário explica, mês a mês,
                      se o documento não foi localizado, está em validação ou possui conflito.
                    </p>
                  </div>
                  <a
                    className="finance-month-link"
                    href="/financas/cobertura#payroll-matrix-title"
                  >
                    Conferir cobertura da folha →
                  </a>
                </aside>
              ) : null}
            </>
          ) : (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Folha mensal ainda não disponível nesta projeção</strong>
                <p>
                  Isso não significa gasto zero. O portal só publica o mês quando
                  todos os subtotais fecham com o total do PDF oficial.
                </p>
              </div>
            </div>
          )}
          <FinanceNonpayrollWorkforceCoverage
            rows={nonpayrollWorkforceCoverageRows}
          />
        </section>

        <FinanceAnnualSummary summaries={annualFinanceSummaries} />

        {monthlyClosures.length > 0 ? (
          <section aria-labelledby="monthly-closure-title" className="monthly-closure-section">
            <div className="section-heading compact">
              <span className="eyebrow">Fechamento do mês</span>
              <h2 id="monthly-closure-title">Uma leitura única das contas</h2>
              <p>
                Cada cartão reúne a receita declarada e os pagamentos do mesmo mês.
                O resultado é calculado por código e só aparece quando as fontes têm
                cobertura comparável. A visão geral mostra os seis fechamentos mais
                recentes; a auditoria de cobertura preserva toda a série.
              </p>
            </div>
            <div className="digest-grid">
              {recentMonthlyClosures.map((closure) => (
                <article className="digest-card monthly-closure-card" key={closure.closureId}>
                  <div className="track-top">
                    <span>{closure.publicBodyName}</span>
                    <span className={`finance-closure-badge finance-closure-${closure.closureStatus}`}>
                      {closureStatusLabel(closure.closureStatus)}
                    </span>
                  </div>
                  <h3 className="procurement-object finance-month-title">
                    {formatMonthTitle(closure.periodEnd)}
                  </h3>
                  <p className="finance-period-note">
                    Competência: {formatDate(closure.periodStart)} a {formatDate(closure.periodEnd)}
                  </p>
                  <div className="monthly-closure-reading">
                    <strong>Comentário do mês</strong>
                    <p>{closure.aiCommentary ?? explainClosure(closure)}</p>
                    {closure.aiCommentary ? (
                      <small className="finance-ai-note">
                        Texto explicativo assistido por IA; os valores e o estado do fechamento
                        são calculados deterministicamente.
                      </small>
                    ) : null}
                  </div>
                  <dl className="procurement-values finance-key-values">
                    <div className="finance-positive-value">
                      <dt>Receita declarada no relatório<small>não é soma das linhas hierárquicas</small></dt>
                      <dd>{formatAmount(closure.revenueReportAmount)}</dd>
                    </div>
                    <div className="finance-negative-value">
                      <dt>Pagamentos efetivados<small>dinheiro que saiu do caixa</small></dt>
                      <dd>{formatAmount(closure.expensePaidAmount)}</dd>
                    </div>
                    <div className={financeDifferenceClass(closure.operationalDifferenceAmount)}>
                      <dt>Diferença operacional<small>receita declarada menos pagamentos</small></dt>
                      <dd>{formatAmount(closure.operationalDifferenceAmount, "aguardando reconciliação")}</dd>
                    </div>
                  </dl>
                  <details className="finance-details">
                    <summary>Ver cobertura e memória de cálculo</summary>
                    <p className="finance-details-note">{closure.coverageNote}</p>
                    <dl className="procurement-values">
                      <div><dt>Relatórios de receita usados</dt><dd>{closure.revenueReportCount.toLocaleString("pt-BR")}</dd></div>
                      <div><dt>Linhas de receita preservadas</dt><dd>{closure.revenueLineCount.toLocaleString("pt-BR")}</dd></div>
                      <div><dt>Relatórios de despesa usados</dt><dd>{closure.expenseReportCount.toLocaleString("pt-BR")}</dd></div>
                      {closure.expenseCommittedAmount ? <div><dt>Empenhado no período</dt><dd>{formatBrlDecimal(closure.expenseCommittedAmount)}</dd></div> : null}
                      {closure.expenseLiquidatedAmount ? <div><dt>Liquidado no período</dt><dd>{formatBrlDecimal(closure.expenseLiquidatedAmount)}</dd></div> : null}
                    </dl>
                    <p className="act-evidence">Metodologia determinística: {closure.calculationMethodology}. Receita usa o total declarado por documento; despesas usam o pagamento efetivado do relatório publicado.</p>
                  </details>
                  <a className="finance-month-link" href={monthlyFinanceHref(closure.periodStart)}>
                    Abrir este mês e conferir as fontes →
                  </a>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {signalsResult.state === "available" ? (
          <section className="finance-signals-section" aria-labelledby="finance-signals-title">
            <div className="section-heading compact">
              <span className="eyebrow">Sinais para contexto</span>
              <h2 id="finance-signals-title">O que merece uma conferência</h2>
              <p>
                São verificações automáticas de consistência e duplicidade nos documentos publicados.
                Um sinal orienta a leitura e não prova irregularidade, fraude ou corrupção.
                A visão geral mostra até seis sinais recentes.
              </p>
            </div>
            {financeSignals.length === 0 ? (
              <article className="digest-card finance-signal-card">
                <strong>Nenhum sinal pendente nesta janela</strong>
                <p className="finance-signal-explanation">
                  As regras foram executadas sobre os relatórios financeiros publicados e não
                  encontraram, até agora, duplicidade ou relação contábil que exija conferência.
                </p>
              </article>
            ) : null}
            <div className="digest-grid">
              {recentFinanceSignals.map((signal) => (
                <article className="digest-card finance-signal-card" key={signal.findingId}>
                  <div className="track-top">
                    <span>{signal.publicBodyName}</span>
                    <span className={`finance-signal-badge finance-signal-${signal.severity}`}>
                      {signalSeverityLabel(signal.severity)}
                    </span>
                  </div>
                  <h3 className="procurement-object">{signal.ruleName}</h3>
                  <p className="finance-period-note">
                    Período: {formatDate(signal.periodStart)} a {formatDate(signal.periodEnd)}
                  </p>
                  <p className="finance-signal-explanation">{signal.publicExplanation}</p>
                  <details className="finance-details">
                    <summary>Ver como o sinal foi calculado</summary>
                    <p className="finance-details-note">
                      Regra versionada <code>{signal.ruleSlug}</code>. O cálculo usa apenas os valores
                      determinísticos do relatório validado e pode ser refeito a qualquer momento.
                    </p>
                    {signal.sourceUrl ? (
                      <p className="act-evidence">
                        <a href={signal.sourceUrl} target="_blank" rel="noreferrer">Ver fonte oficial</a>
                        {signal.artifactSha256 ? ` · hash ${signal.artifactSha256.slice(0, 12)}…` : null}
                      </p>
                    ) : null}
                  </details>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {sortedExpenseReports.length > 0 ? (
          <section aria-labelledby="expense-title">
            <div className="section-heading compact">
              <span className="eyebrow">Despesas</span>
              <h2 id="expense-title">Quanto saiu do caixa</h2>
              <p>
                Este é o valor efetivamente pago pela Prefeitura no período do
                relatório. A visão geral mostra {recentExpenseReports.length.toLocaleString("pt-BR")} meses
                recentes de um total de {sortedExpenseReports.length.toLocaleString("pt-BR")} relatórios;
                o calendário acima mantém o acesso às demais competências.
              </p>
            </div>
            <div className="digest-grid">
              {recentExpenseReports.map((report) => (
                <article className="digest-card finance-negative-card" key={report.expenseReportId}>
                  <div className="track-top">
                    <span>{report.publicBodyName}</span>
                    <span className="track-status">{report.fiscalYear}</span>
                  </div>
                  <h3 className="procurement-object finance-month-title">
                    {formatMonthTitle(report.periodEnd)}
                  </h3>
                  <p className="finance-period-note">
                    Mês analisado: {formatPeriod(report)} · Prefeitura Municipal de Barreiras
                  </p>
                  <div className="finance-reading finance-reading-card">
                    <strong>Resumo para o cidadão</strong>
                    <p>
                      Entre {formatDate(report.periodStart)} e {formatDate(report.periodEnd)},
                      a Prefeitura pagou {formatBrlDecimal(report.totalPaidPeriodAmount)}.
                      Desde o início do ano, o total pago chegou a {formatBrlDecimal(report.totalPaidToDateAmount)}.
                    </p>
                  </div>
                  <dl className="procurement-values finance-key-values">
                    <div className="revenue-primary-value">
                      <dt>
                        Saiu do caixa no mês
                        <small>pagamento efetivo</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalPaidPeriodAmount)}</dd>
                    </div>
                    <div>
                      <dt>
                        Saiu do caixa no ano
                        <small>pagamento acumulado</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalPaidToDateAmount)}</dd>
                    </div>
                    <div>
                      <dt>
                        Orçamento atualizado
                        <small>limite ajustado, não é gasto</small>
                      </dt>
                      <dd>{formatBrlDecimal(report.totalUpdatedAmount)}</dd>
                    </div>
                  </dl>
                  <details className="finance-details">
                    <summary>Ver detalhes contábeis deste mês</summary>
                    <dl className="procurement-values">
                      <div>
                        <dt>
                          Entrega conferida
                          <small>liquidado no período</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalLiquidatedPeriodAmount)}</dd>
                      </div>
                      <div>
                        <dt>
                          Valor reservado
                          <small>empenhado no período</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalCommittedPeriodAmount)}</dd>
                      </div>
                      <div>
                        <dt>
                          Saldo informado
                          <small>diferença registrada no relatório</small>
                        </dt>
                        <dd>{formatBrlDecimal(report.totalBalanceAmount)}</dd>
                      </div>
                    </dl>
                    <p className="finance-details-note">
                      Empenhado, liquidado e pago são etapas diferentes. O site não
                      soma esses valores entre si.
                    </p>
                    <p className="act-evidence">
                      <a href={report.documentSourceUrl} target="_blank" rel="noreferrer">
                        Ver PDF oficial
                      </a>{" "}
                      <a href={report.sourceUrl} target="_blank" rel="noreferrer">
                        Ver resposta da API
                      </a>{" "}
                      · PDF preservado · hash {report.documentArtifactSha256.slice(0, 12)}…
                      · publicado após validação determinística em {formatCollectedAt(report.collectedAt)}
                    </p>
                  </details>
                </article>
              ))}
            </div>
            {latestExpenseReport ? (
              <a
                className="finance-month-link"
                href={monthlyFinanceHref(latestExpenseReport.periodStart)}
              >
                Abrir o mês e ver as 25 maiores linhas pagas →
              </a>
            ) : null}
          </section>
        ) : null}

        {sortedRevenues.length > 0 ? (
          <section aria-labelledby="revenue-title">
            <div className="section-heading compact">
              <span className="eyebrow">Dinheiro que entrou</span>
              <h2 id="revenue-title">Receitas da Prefeitura</h2>
              <p>
                O último período disponível é {latestRevenue ? formatDate(latestRevenue) : "não informado"}.
                A visão geral mostra {recentRevenues.length.toLocaleString("pt-BR")} lançamentos recentes
                de um total de {sortedRevenues.length.toLocaleString("pt-BR")}; os demais ficam no detalhe
                mensal para não misturar competências e códigos diferentes.
              </p>
            </div>
            <div className="finance-reading" role="note">
              <strong>Como ler esta parte</strong>
              <p>
                Receita é dinheiro que entrou nos cofres públicos. “No período”
                mostra o intervalo do lançamento; “acumulado” é o total informado
                até aquela data. Não somamos os cartões entre si, porque códigos
                diferentes podem representar partes da mesma conta.
              </p>
            </div>
            <details className="finance-details">
              <summary>Ver lançamentos detalhados de receitas</summary>
              <p className="finance-details-note">
                Cada cartão é uma linha do relatório oficial. Use os links dentro
                dos cartões para abrir o documento e a resposta original.
              </p>
              <div className="digest-grid">
              {recentRevenues.map((revenue) => (
                  <article
                    className={`digest-card ${
                      revenue.collectionDirection !== "credit"
                        ? "finance-negative-card"
                        : "finance-positive-card"
                    }`}
                    key={revenue.revenueId}
                  >
                  <div className="track-top">
                    <span>{revenue.publicBodyName}</span>
                    <span className="track-status">{revenue.fiscalYear}</span>
                  </div>
                  <h3 className="procurement-object">{revenue.description}</h3>
                  <dl className="procurement-values">
                    <div className="revenue-primary-value">
                      <dt>
                        {revenue.collectionDirection === "deduction"
                          ? "Deduções no período"
                          : revenue.collectionDirection === "adjustment"
                            ? "Ajuste negativo no período"
                            : "Valor arrecadado no período"}
                      </dt>
                      <dd>{formatBrlDecimal(revenue.collectedAmount)}</dd>
                    </div>
                    <div>
                      <dt>Acumulado no relatório</dt>
                      <dd>{formatBrlDecimal(revenue.accumulatedAmount)}</dd>
                    </div>
                    <div>
                      <dt>Total declarado no relatório</dt>
                      <dd>{formatBrlDecimal(revenue.reportTotalPeriodAmount)}</dd>
                    </div>
                    <div>
                      <dt>Data da receita</dt>
                      <dd>{formatDate(revenue.revenueDate)}</dd>
                    </div>
                    {revenue.revenueCode ? (
                      <div>
                        <dt>Código</dt>
                        <dd>{revenue.revenueCode}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <div className="finance-reading finance-reading-card">
                    <strong>Leitura rápida</strong>
                    <p>{explainRevenue(revenue)}</p>
                  </div>
                  <p className="act-evidence">
                    {revenue.documentSourceUrl ? (
                      <a
                        href={revenue.documentSourceUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Ver PDF oficial
                      </a>
                    ) : null}{" "}
                    {revenue.sourceUrl ? (
                      <a href={revenue.sourceUrl} target="_blank" rel="noreferrer">
                        Ver resposta da API
                      </a>
                    ) : null}{" "}
                    · PDF preservado · hash {revenue.documentArtifactSha256.slice(0, 12)}…
                    · publicado após validação determinística em {formatCollectedAt(revenue.collectedAt)}
                  </p>
                </article>
              ))}
              </div>
            </details>
          </section>
        ) : null}

        {publicObligations.length > 0 ? (
          <section
            aria-labelledby="public-obligation-title"
            className="finance-documents finance-obligation-documents"
          >
            <div className="section-heading compact">
              <span className="eyebrow">Compromissos de outros períodos</span>
              <h2 id="public-obligation-title">Restos a pagar pagos pela Prefeitura</h2>
              <p>
                Restos a pagar são despesas empenhadas em período anterior e pagas
                depois. O valor abaixo é o que o balancete declara como pago no mês;
                não é o total da dívida municipal nem deve ser somado novamente às
                despesas do mesmo relatório.
              </p>
            </div>
            {latestPublicObligation ? (
              <article className="finance-status-panel finance-obligation-latest">
                <div>
                  <span className="eyebrow">Último mês com valor publicado</span>
                  <h2>
                    {formatMonthTitle(
                      latestPublicObligation.periodStart ?? latestPublicObligation.periodEnd,
                    )}
                  </h2>
                  <p>
                    O balancete oficial informa quanto saiu do caixa neste mês para
                    quitar despesas empenhadas anteriormente. Este valor não é o total
                    da dívida municipal nem informa, sozinho, quanto ainda falta pagar.
                  </p>
                </div>
                <span className="finance-status-pill finance-obligation-latest-value">
                  {latestPublicObligation.paymentsPeriodAmount
                    ? formatBrlDecimal(latestPublicObligation.paymentsPeriodAmount)
                    : "valor não informado"}
                </span>
              </article>
            ) : null}
            <div
              className="finance-coverage-summary"
              aria-label="Resumo da cobertura de restos a pagar"
            >
              <div>
                <strong>{publishedObligationMonths.toLocaleString("pt-BR")}</strong>
                <span>competências com valor</span>
              </div>
              <div>
                <strong>{obligationSectionAbsentMonths.toLocaleString("pt-BR")}</strong>
                <span>competências com seção ausente</span>
              </div>
              <div>
                <strong>{obligationSectionIncompleteMonths.toLocaleString("pt-BR")}</strong>
                <span>competências com fonte incompleta</span>
              </div>
              <div>
                <strong>{obligationSourceConflictMonths.toLocaleString("pt-BR")}</strong>
                <span>competências com divergência oficial</span>
              </div>
            </div>
            <details className="finance-details finance-obligation-history">
              <summary>
                Ver histórico mês a mês: {recentPublicObligations.length.toLocaleString("pt-BR")} recentes de{" "}
                {publicObligations.length.toLocaleString("pt-BR")} competências publicadas
              </summary>
              <div className="digest-grid">
                {recentPublicObligations.map((obligation: PublicObligation) => (
                  <article
                    className="digest-card finance-negative-card"
                    key={obligation.obligationId}
                  >
                    <div className="track-top">
                      <span>Restos a pagar</span>
                      <span className="track-status">
                        {formatMonthTitle(obligation.periodStart ?? obligation.periodEnd)}
                      </span>
                    </div>
                    <h3 className="procurement-object">
                      Pagamentos realizados no mês
                    </h3>
                    <dl className="procurement-values">
                      <div className="revenue-primary-value">
                        <dt>Saiu do caixa no mês</dt>
                        <dd>
                          {obligation.paymentsPeriodAmount
                            ? formatBrlDecimal(obligation.paymentsPeriodAmount)
                            : "valor não informado"}
                        </dd>
                      </div>
                    </dl>
                    <div className="finance-reading finance-reading-card">
                      <strong>Em palavras simples</strong>
                      <p>
                        Este valor saiu dos cofres no mês para quitar despesas que já
                        haviam sido empenhadas antes. Ele mostra pagamento realizado,
                        não quanto ainda falta pagar.
                      </p>
                    </div>
                    <details className="finance-details">
                      <summary>Ver acumulados e fonte oficial</summary>
                      <dl className="procurement-values">
                        <div>
                          <dt>Pago até o mês anterior</dt>
                          <dd>
                            {obligation.paymentsPriorAmount
                              ? formatBrlDecimal(obligation.paymentsPriorAmount)
                              : "não informado"}
                          </dd>
                        </div>
                        <div>
                          <dt>Pago até o fim deste mês</dt>
                          <dd>
                            {obligation.paymentsToDateAmount
                              ? formatBrlDecimal(obligation.paymentsToDateAmount)
                              : "não informado"}
                          </dd>
                        </div>
                      </dl>
                      <p className="act-evidence">
                        <a
                          href={obligation.documentSourceUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Abrir balancete oficial →
                        </a>{" "}
                        · PDF preservado · hash{" "}
                        {obligation.documentArtifactSha256.slice(0, 12)}…
                      </p>
                    </details>
                  </article>
                ))}
              </div>
            </details>
          </section>
        ) : null}

        {obligationCoverageGapCount > 0 ? (
          <aside
            className="finance-status-panel"
            aria-label="Cobertura incompleta de restos a pagar"
          >
            <div>
              <span className="eyebrow">Cobertura e lacunas</span>
              <strong>
                {obligationCoverageGapCount.toLocaleString("pt-BR")} competências sem valor publicado
              </strong>
              <p>
                Documento ausente, seção incompleta e divergência entre fontes não
                são tratados como R$ 0 nem como prova de irregularidade. O calendário
                informa o motivo de cada lacuna.
              </p>
            </div>
            <a
              className="finance-month-link"
              href="/financas/cobertura#obligation-matrix-title"
            >
              Conferir cobertura de restos a pagar →
            </a>
          </aside>
        ) : null}

        <section aria-labelledby="obligation-document-title" className="finance-documents finance-obligation-documents">
          <div className="section-heading compact">
            <span className="eyebrow">Passivos públicos</span>
            <h2 id="obligation-document-title">Dívidas e obrigações em apuração</h2>
            <p>
              Balancetes, DCA e RGF são fontes para identificar empréstimos,
              precatórios, restos a pagar e outras obrigações. Um documento isolado não
              representa o total da dívida municipal; os valores só serão consolidados
              depois de reconciliar período, natureza, saldo e retificações.
            </p>
          </div>
          {obligationDocuments.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Documentos-base ainda não preservados nesta projeção</strong>
                <p>
                  A coleta foi preparada para balancetes e demonstrativos fiscais. Enquanto os
                  artefatos não forem preservados e validados, o portal não exibirá um
                  número de dívida sem sustentação.
                </p>
                <a
                  href="https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Consultar a fonte oficial →
                </a>
              </div>
            </div>
          ) : (
            <details className="finance-details">
              <summary>
                Ver {recentObligationDocuments.length.toLocaleString("pt-BR")} documentos-base recentes de{" "}
                {obligationDocuments.length.toLocaleString("pt-BR")}
              </summary>
              <div className="digest-grid">
                {recentObligationDocuments.map((document) => (
                  <article className="digest-card finance-debt-card" key={document.documentId}>
                    <div className="track-top">
                      <span>{financeResourceLabel(document.sourceResource)}</span>
                      <span className="track-status">
                        {document.fiscalYear ?? "ano não informado"}
                      </span>
                    </div>
                    <h3 className="procurement-object">{document.title}</h3>
                    <dl className="procurement-values">
                      <div>
                        <dt>Referência</dt>
                        <dd>{document.referenceDate ?? "não informada"}</dd>
                      </div>
                      {document.description ? (
                        <div>
                          <dt>Descrição</dt>
                          <dd>{document.description}</dd>
                        </div>
                      ) : null}
                    </dl>
                    <p className="act-evidence">
                      <a href={document.documentUrl} target="_blank" rel="noreferrer">
                        Abrir documento oficial →
                      </a>{" "}
                      · resposta da API preservada · {document.documentPreserved
                        ? "documento preservado"
                        : "documento ainda não preservado"}{" "}
                      · hash {document.artifactSha256.slice(0, 12)}…
                    </p>
                  </article>
                ))}
              </div>
            </details>
          )}
        </section>

        {municipalControlDocuments.length > 0 ? (
          <section
            aria-labelledby="municipal-control-document-title"
            className="finance-documents"
          >
            <div className="section-heading compact">
              <span className="eyebrow">Base legal municipal</span>
              <h2 id="municipal-control-document-title">
                Controle e prestação de contas
              </h2>
              <p>
                Esta série do Portal da Prefeitura reúne leis e fundamentos de
                controle. Ela não contém os demonstrativos anuais nem autoriza
                calcular receitas, despesas ou saldo. As contas anuais comparáveis
                são publicadas separadamente na DCA do Tesouro.
              </p>
              <p>
                <a href="/financas/base-legal">
                  Pesquisar e ler o texto integral da base legal →
                </a>
              </p>
            </div>
            <details className="finance-details">
              <summary>
                Ver {municipalControlDocuments.length.toLocaleString("pt-BR")} registros
                da base legal
              </summary>
              <div className="digest-grid">
                {municipalControlDocuments.map((document) => (
                  <article className="digest-card" key={document.documentId}>
                    <div className="track-top">
                      <span>{financeResourceLabel(document.sourceResource)}</span>
                      <span className="track-status">
                        {document.fiscalYear ?? "ano não informado"}
                      </span>
                    </div>
                    <h3 className="procurement-object">{document.title}</h3>
                    {document.description ? <p>{document.description}</p> : null}
                    <p className="act-evidence">
                      <a href={document.documentUrl} target="_blank" rel="noreferrer">
                        Abrir documento oficial →
                      </a>{" "}
                      · resposta da API preservada · {document.documentPreserved
                        ? "documento preservado"
                        : "documento ainda não preservado"}{" "}
                      · hash {document.artifactSha256.slice(0, 12)}…
                    </p>
                  </article>
                ))}
              </div>
            </details>
          </section>
        ) : null}

        <section aria-labelledby="document-title" className="finance-documents">
          <div className="section-heading compact">
            <span className="eyebrow">Documentos oficiais</span>
            <h2 id="document-title">O que a Prefeitura publicou</h2>
            <p>
              {operationalDocuments.length > 0
                ? `${operationalDocuments.length.toLocaleString("pt-BR")} documentos no catálogo. A lista abaixo mostra os ${recentOperationalDocuments.length.toLocaleString("pt-BR")} mais recentes; a auditoria de cobertura dá acesso por competência.`
                : "Ainda não há documentos mensais de execução ou arrecadação disponíveis."}
            </p>
          </div>

          {operationalDocuments.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Nenhum documento mensal preservado ainda</strong>
                <p>
                  Isso não significa receita ou despesa zero. Os demonstrativos
                  fiscais RREO/RGF aparecem em uma seção separada porque não são
                  fechamentos mensais.
                </p>
                <a
                  href="https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Consultar a fonte oficial →
                </a>
              </div>
            </div>
          ) : (
            <details className="finance-details">
              <summary>
                Ver {recentOperationalDocuments.length.toLocaleString("pt-BR")} documentos mais recentes
              </summary>
              <div className="digest-grid">
              {recentOperationalDocuments.map((document) => (
                <article className="digest-card" key={document.documentId}>
                  <div className="track-top">
                    <span>{financeResourceLabel(document.sourceResource)}</span>
                    <span className="track-status">
                      {document.fiscalYear ?? "período não informado"}
                    </span>
                  </div>
                  <h3 className="procurement-object">{document.title}</h3>
                  <dl className="procurement-values">
                    <div>
                      <dt>Referência</dt>
                      <dd>{document.referenceDate ?? "não informada"}</dd>
                    </div>
                    {document.description ? (
                      <div>
                        <dt>Descrição</dt>
                        <dd>{document.description}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <p className="act-evidence">
                    <a href={document.documentUrl} target="_blank" rel="noreferrer">
                      Abrir documento oficial →
                    </a>{" "}
                    · resposta da API preservada · {document.documentPreserved
                      ? "PDF preservado"
                      : "PDF ainda não preservado"}{" "}
                    · hash {document.artifactSha256.slice(0, 12)}…
                  </p>
                </article>
              ))}
              </div>
            </details>
          )}
        </section>

        {fiscalDocuments.length > 0 ? (
          <section aria-labelledby="fiscal-document-title" className="finance-documents finance-fiscal-documents">
            <div className="section-heading compact">
              <span className="eyebrow">Demonstrativos fiscais</span>
              <h2 id="fiscal-document-title">RREO e RGF: a visão fiscal mais ampla</h2>
              <p>
                Estes relatórios mostram metas fiscais, resultados e limites em
                períodos bimestrais ou quadrimestrais. Eles ajudam a acompanhar
                2021 e anos anteriores, mas não substituem o fechamento mensal de
                receitas e despesas.
              </p>
            </div>
            <details className="finance-details">
              <summary>
                Ver {recentFiscalDocuments.length.toLocaleString("pt-BR")} demonstrativos fiscais recentes de{" "}
                {fiscalDocuments.length.toLocaleString("pt-BR")}
              </summary>
              <div className="digest-grid">
                {recentFiscalDocuments.map((document) => (
                  <article className="digest-card" key={document.documentId}>
                    <div className="track-top">
                      <span>{financeResourceLabel(document.sourceResource)}</span>
                      <span className="track-status">{document.fiscalYear ?? "ano não informado"}</span>
                    </div>
                    <h3 className="procurement-object">{document.title}</h3>
                    <dl className="procurement-values">
                      <div>
                        <dt>Data de referência</dt>
                        <dd>{document.referenceDate ?? "não informada"}</dd>
                      </div>
                      {document.description ? (
                        <div>
                          <dt>Descrição</dt>
                          <dd>{document.description}</dd>
                        </div>
                      ) : null}
                    </dl>
                    <p className="act-evidence">
                      <a href={document.documentUrl} target="_blank" rel="noreferrer">
                        Abrir documento oficial →
                      </a>{" "}
                      · resposta da API preservada · {document.documentPreserved
                        ? "PDF preservado"
                        : "PDF ainda não preservado"}{" "}
                      · hash {document.artifactSha256.slice(0, 12)}…
                    </p>
                  </article>
                ))}
              </div>
            </details>
          </section>
        ) : null}

        <p className="hero-note">
          Metodologia: empenho, liquidação, pagamento e receita são estágios
          diferentes. O Barreiras 360 não soma esses estágios como se fossem a
          mesma coisa. Deduções são exibidas com sinal negativo e só aparecem
          quando o PDF, o período, o hash e a estrutura do relatório passam por
          validação determinística.
        </p>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="/">
              <span>Barreiras 360</span>
            </a>
            <p>Informação pública de Barreiras para acompanhar a cidade com clareza.</p>
          </div>
          <div className="footer-status">
            <span className="status-dot" />
            Receitas e documentos somente com fonte e evidência
          </div>
        </div>
      </footer>
    </main>
  );
}
