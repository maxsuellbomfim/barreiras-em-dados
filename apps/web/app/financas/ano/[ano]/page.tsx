import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  buildAnnualFinanceTrend,
  parseFinanceYearSlug,
  type AnnualFinanceTrendMonth,
} from "../../../../lib/annual-finance-trend.mjs";
import { buildAnnualExpenseBudgetUnits } from "../../../../lib/annual-expense-budget-units.mjs";
import { buildAnnualExpenseCategories } from "../../../../lib/annual-expense-categories.mjs";
import { summarizeAnnualFinances } from "../../../../lib/annual-finance-summary.mjs";
import { getPublicExpenseBudgetUnitSummary } from "../../../../lib/expense-budget-unit-summary.mjs";
import { getPublicExpenseCategorySummary } from "../../../../lib/expense-category-summary.mjs";
import { getPublicExpenseReports } from "../../../../lib/expenses";
import { getPublicExpenseReportSourceConflicts } from "../../../../lib/expense-report-source-conflicts.mjs";
import { getPublicMonthlyFinanceClosures } from "../../../../lib/monthly-finance";
import { monthlyFinanceHref } from "../../../../lib/monthly-finance-detail.mjs";
import { formatBrlDecimal } from "../../../../lib/revenues";
import { FinanceAnnualBudgetUnits } from "./finance-annual-budget-units";
import { FinanceAnnualExpenseCategories } from "./finance-annual-expense-categories";
import { FinanceAnnualSourceConflicts } from "./finance-annual-source-conflicts";

export const revalidate = 300;

type PageProps = Readonly<{
  params: Promise<{ ano: string }>;
}>;

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  timeZone: "America/Bahia",
});

function currentBahiaYear(): number {
  return Number(
    new Intl.DateTimeFormat("en", {
      year: "numeric",
      timeZone: "America/Bahia",
    }).format(new Date()),
  );
}

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function statusLabel(status: AnnualFinanceTrendMonth["closureStatus"]): string {
  if (status === "operational") return "Fechamento comparável";
  if (status === "needs_review") return "Em reconciliação";
  if (status === "needs_data") return "Dados parciais";
  return "Sem fechamento localizado";
}

function differenceClass(value: string | null): string {
  return value?.startsWith("-")
    ? "finance-negative-value"
    : value
      ? "finance-positive-value"
      : "";
}

function barWidth(basisPoints: number | null): string {
  return basisPoints === null ? "0%" : `${basisPoints / 100}%`;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { ano } = await params;
  const fiscalYear = parseFinanceYearSlug(ano, currentBahiaYear());
  if (!fiscalYear) return { title: "Ano inválido | Finanças" };
  return {
    title: `Finanças de ${fiscalYear}`,
    description: `Receitas e pagamentos mensais de Barreiras em ${fiscalYear}, com cobertura e documentos oficiais verificáveis.`,
  };
}

export default async function AnnualFinancePage({ params }: PageProps) {
  const { ano } = await params;
  const fiscalYear = parseFinanceYearSlug(ano, currentBahiaYear());
  if (!fiscalYear) notFound();

  const [result, expenseReportsResult, sourceConflictsResult] = await Promise.all([
    getPublicMonthlyFinanceClosures(fiscalYear),
    getPublicExpenseReports(fiscalYear),
    getPublicExpenseReportSourceConflicts(fiscalYear),
  ]);
  const closures = result.state === "available" ? result.closures : [];
  const trend = result.state === "available"
    ? buildAnnualFinanceTrend(closures, fiscalYear)
    : { state: "unavailable" as const };
  const summary = trend.state === "available"
    ? summarizeAnnualFinances(closures).find((item) => item.fiscalYear === fiscalYear) ?? null
    : null;
  const comparablePeriods = new Set(
    closures
      .filter((closure) => closure.closureStatus === "operational")
      .map((closure) => closure.periodStart),
  );
  const expenseReports = expenseReportsResult.state === "available"
    ? expenseReportsResult.reports.filter((report) => comparablePeriods.has(report.periodStart))
    : [];
  const reportBreakdowns = expenseReportsResult.state === "available"
    ? await Promise.all(
        expenseReports.map(async (report) => {
          const [categories, budgetUnits] = await Promise.all([
            getPublicExpenseCategorySummary(report.expenseReportId),
            getPublicExpenseBudgetUnitSummary(report.expenseReportId),
          ]);
          return { reportId: report.expenseReportId, categories, budgetUnits } as const;
        }),
      )
    : [];
  const categorySummaries = new Map(
    reportBreakdowns.map((item) => [item.reportId, item.categories] as const),
  );
  const budgetUnitSummaries = new Map(
    reportBreakdowns.map((item) => [item.reportId, item.budgetUnits] as const),
  );
  const annualExpenseCategories =
    result.state === "available" && expenseReportsResult.state === "available"
      ? buildAnnualExpenseCategories({
          fiscalYear,
          closures,
          reports: expenseReportsResult.reports,
          summariesByReport: categorySummaries,
        })
      : { state: "unavailable" as const };
  const annualBudgetUnits =
    result.state === "available" && expenseReportsResult.state === "available"
      ? buildAnnualExpenseBudgetUnits({
          fiscalYear,
          closures,
          reports: expenseReportsResult.reports,
          summariesByReport: budgetUnitSummaries,
        })
      : { state: "unavailable" as const };

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/financas"><span>← Finanças</span></a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/licitacoes">Compras</a>
            <a href="/representantes">Quem decide</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section finance-year-page" aria-labelledby="finance-year-title">
        <div className="section-heading">
          <span className="eyebrow">Visão anual verificável</span>
          <h1 id="finance-year-title">As contas de {fiscalYear}, mês a mês</h1>
          <p>
            Compare a receita declarada e os pagamentos de cada competência. Só há
            barras quando os dois relatórios oficiais do mês foram reconciliados.
          </p>
        </div>

        {trend.state === "unavailable" ? (
          <div className="finance-year-unavailable" role="status">
            <strong>Não foi possível montar a série anual agora</strong>
            <p>Nenhum valor foi estimado ou substituído por zero. Tente novamente mais tarde.</p>
          </div>
        ) : (
          <>
            <div className="finance-year-coverage" role="status">
              <strong>{trend.comparableMonthCount} de 12 meses</strong>
              <span>têm receita e pagamentos comparáveis</span>
            </div>

            {summary ? (
              <dl className="finance-year-totals">
                <div className="finance-positive-value">
                  <dt>Receita declarada no recorte</dt>
                  <dd>{formatBrlDecimal(summary.revenueAmount)}</dd>
                </div>
                <div className="finance-negative-value">
                  <dt>Pagamentos no recorte</dt>
                  <dd>{formatBrlDecimal(summary.paidAmount)}</dd>
                </div>
                <div className={differenceClass(summary.operationalDifferenceAmount)}>
                  <dt>Diferença operacional</dt>
                  <dd>{formatBrlDecimal(summary.operationalDifferenceAmount)}</dd>
                </div>
              </dl>
            ) : (
              <div className="finance-year-unavailable" role="status">
                <strong>Nenhum mês comparável localizado neste ano</strong>
                <p>Isso não significa receita ou gasto zero; significa ausência de fechamento reconciliado.</p>
              </div>
            )}

            <section className="finance-year-chart" aria-labelledby="finance-year-chart-title">
              <div className="section-heading compact">
                <span className="eyebrow">Evolução mensal</span>
                <h2 id="finance-year-chart-title">Quanto entrou e quanto foi pago</h2>
                <p>
                  O comprimento das barras usa o maior valor mensal deste ano como
                  referência visual. Os números em reais continuam sendo os valores oficiais.
                </p>
              </div>
              <div className="finance-year-legend" aria-label="Legenda do gráfico">
                <span><i className="finance-year-revenue-swatch" /> Receita declarada</span>
                <span><i className="finance-year-paid-swatch" /> Pagamentos</span>
              </div>
              <ol className="finance-year-months">
                {trend.months.map((month) => {
                  const operational = month.closureStatus === "operational";
                  return (
                    <li key={month.periodStart} className={operational ? "" : "finance-year-month-missing"}>
                      <div className="finance-year-month-heading">
                        <div>
                          <strong>{formatMonth(month.periodStart)}</strong>
                          <span>{statusLabel(month.closureStatus)}</span>
                        </div>
                        <a href={monthlyFinanceHref(month.periodStart)}>Abrir mês →</a>
                      </div>
                      {operational ? (
                        <>
                          <div className="finance-year-bars" aria-hidden="true">
                            <span className="finance-year-revenue-bar" style={{ width: barWidth(month.revenueBarBasisPoints) }} />
                            <span className="finance-year-paid-bar" style={{ width: barWidth(month.paidBarBasisPoints) }} />
                          </div>
                          <dl>
                            <div><dt>Receita</dt><dd>{formatBrlDecimal(month.revenueAmount!)}</dd></div>
                            <div><dt>Pago</dt><dd>{formatBrlDecimal(month.paidAmount!)}</dd></div>
                            <div className={differenceClass(month.operationalDifferenceAmount)}>
                              <dt>Diferença</dt><dd>{formatBrlDecimal(month.operationalDifferenceAmount!)}</dd>
                            </div>
                          </dl>
                        </>
                      ) : (
                        <p className="finance-year-missing-copy">
                          Nenhum valor é mostrado porque o fechamento do mês não está comparável.
                        </p>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>

            <FinanceAnnualSourceConflicts result={sourceConflictsResult} />

            <FinanceAnnualBudgetUnits result={annualBudgetUnits} />

            <FinanceAnnualExpenseCategories result={annualExpenseCategories} />

            <p className="finance-annual-method">
              Totais e escalas calculados em centavos por código determinístico. A
              diferença operacional não é saldo bancário, superávit nem déficit fiscal.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
