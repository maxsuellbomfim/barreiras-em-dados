import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  monthlyFinanceStatusCopy,
  periodStartFromSlug,
  selectMonthlyExpenseReportId,
  type MonthlyFinanceExpenseDocument,
  type MonthlyFinanceRevenueDocument,
} from "../../../lib/monthly-finance-detail.mjs";
import {
  getPublicExpenseLines,
  getPublicExpenseReports,
  type PublicExpenseLine,
} from "../../../lib/expenses";
import { getPublicMonthlyFinanceDetail } from "../../../lib/monthly-finance";
import { formatBrlDecimal } from "../../../lib/revenues";

export const revalidate = 300;

type PageProps = Readonly<{
  params: Promise<{ competencia: string }>;
}>;

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function formatDate(value: string): string {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

function formatAmount(value: string | null): string {
  return value === null ? "ainda não disponível" : formatBrlDecimal(value);
}

function shortHash(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { competencia } = await params;
  const periodStart = periodStartFromSlug(competencia);
  if (!periodStart) return { title: "Competência inválida | Finanças" };
  return {
    title: `Contas de ${formatMonth(periodStart)} | Finanças`,
    description: `Receitas, empenhos, liquidações e pagamentos de ${formatMonth(periodStart)}, com documentos oficiais e hashes verificáveis.`,
  };
}

function RevenueEvidence({
  document,
  index,
}: Readonly<{ document: MonthlyFinanceRevenueDocument; index: number }>) {
  return (
    <article className="finance-evidence-card">
      <div>
        <span className="finance-evidence-number" aria-hidden="true">{index + 1}</span>
        <h3>Relatório de receita {index + 1}</h3>
      </div>
      <dl>
        <div><dt>Receita declarada</dt><dd>{formatBrlDecimal(document.reportAmount)}</dd></div>
        <div><dt>Linhas validadas</dt><dd>{document.lineCount.toLocaleString("pt-BR")}</dd></div>
      </dl>
      <div className="finance-evidence-actions">
        <a href={document.documentUrl} target="_blank" rel="noreferrer">Abrir PDF oficial</a>
        <a href={document.sourceUrl} target="_blank" rel="noreferrer">Abrir resposta da fonte</a>
      </div>
      <details className="finance-hash-details">
        <summary>Conferir os hashes preservados</summary>
        <p><strong>PDF:</strong> <code>{document.artifactSha256}</code></p>
        <p><strong>Resposta da fonte:</strong> <code>{document.sourceArtifactSha256}</code></p>
      </details>
    </article>
  );
}

function ExpenseEvidence({
  document,
  index,
}: Readonly<{ document: MonthlyFinanceExpenseDocument; index: number }>) {
  return (
    <article className="finance-evidence-card">
      <div>
        <span className="finance-evidence-number finance-evidence-expense" aria-hidden="true">{index + 1}</span>
        <h3>Relatório de despesa {index + 1}</h3>
      </div>
      <dl>
        <div><dt>Empenhado</dt><dd>{formatBrlDecimal(document.committedAmount)}</dd></div>
        <div><dt>Liquidado</dt><dd>{formatBrlDecimal(document.liquidatedAmount)}</dd></div>
        <div><dt>Pago</dt><dd>{formatBrlDecimal(document.paidAmount)}</dd></div>
      </dl>
      <div className="finance-evidence-actions">
        <a href={document.documentUrl} target="_blank" rel="noreferrer">Abrir PDF oficial</a>
        <a href={document.sourceUrl} target="_blank" rel="noreferrer">Abrir resposta da fonte</a>
      </div>
      <details className="finance-hash-details">
        <summary>Conferir os hashes preservados</summary>
        <p><strong>PDF:</strong> <code>{document.artifactSha256}</code></p>
        <p><strong>Resposta da fonte:</strong> <code>{document.sourceArtifactSha256}</code></p>
      </details>
    </article>
  );
}

function ExpenseLineCard({ line }: Readonly<{ line: PublicExpenseLine }>) {
  return (
    <article className="digest-card finance-negative-card">
      <div className="track-top">
        <span>Linha {line.lineNumber.toLocaleString("pt-BR")}</span>
        <span className="track-status">{line.expenseCode}</span>
      </div>
      <h3 className="procurement-object">{line.description}</h3>
      <dl className="procurement-values">
        <div className="revenue-primary-value">
          <dt>Pago neste mês</dt>
          <dd>{formatBrlDecimal(line.paidPeriodAmount)}</dd>
        </div>
        <div>
          <dt>Empenhado neste mês</dt>
          <dd>{formatBrlDecimal(line.committedPeriodAmount)}</dd>
        </div>
        <div>
          <dt>Liquidado neste mês</dt>
          <dd>{formatBrlDecimal(line.liquidatedPeriodAmount)}</dd>
        </div>
        <div>
          <dt>Valor atualizado</dt>
          <dd>{formatBrlDecimal(line.updatedAmount)}</dd>
        </div>
      </dl>
      <p className="act-evidence">
        Código da fonte {line.sourceCode} ·{" "}
        <a href={line.documentSourceUrl} target="_blank" rel="noreferrer">
          conferir no documento oficial
        </a>
      </p>
    </article>
  );
}

function EmptyMonth({ periodStart }: Readonly<{ periodStart: string }>) {
  return (
    <section className="section finance-month-empty" aria-labelledby="month-empty-title">
      <span className="eyebrow">Competência mensal</span>
      <h1 id="month-empty-title">As contas de {formatMonth(periodStart)} ainda não foram publicadas</h1>
      <p>
        Isso não significa receita ou despesa zero. O Barreiras 360 só publica o
        fechamento quando consegue relacionar os valores aos documentos oficiais.
      </p>
      <a className="finance-month-back" href="/financas">← Voltar para todas as finanças</a>
    </section>
  );
}

export default async function MonthlyFinancePage({ params }: PageProps) {
  const { competencia } = await params;
  const periodStart = periodStartFromSlug(competencia);
  if (!periodStart) notFound();

  const result = await getPublicMonthlyFinanceDetail(periodStart);
  if (result.state === "not_found") return <EmptyMonth periodStart={periodStart} />;
  if (result.state === "unavailable") {
    return (
      <section className="section finance-month-empty" aria-labelledby="month-unavailable-title">
        <span className="eyebrow">Consulta temporariamente indisponível</span>
        <h1 id="month-unavailable-title">Não foi possível consultar este mês agora</h1>
        <p>
          Nenhum valor será substituído por zero ou estimado. Tente novamente mais
          tarde ou consulte a fonte oficial enquanto a conexão é restabelecida.
        </p>
        <a className="finance-month-back" href="/financas">← Voltar para todas as finanças</a>
      </section>
    );
  }

  const { detail } = result;
  const reportsResult = await getPublicExpenseReports(detail.fiscalYear);
  const expenseReportId = selectMonthlyExpenseReportId(
    reportsResult.state === "available" ? reportsResult.reports : [],
    detail,
  );
  const expenseLinesResult = expenseReportId
    ? await getPublicExpenseLines(expenseReportId, 25)
    : { state: "unavailable" as const };
  const expenseLines =
    expenseLinesResult.state === "available" ? expenseLinesResult.lines : [];
  const status = monthlyFinanceStatusCopy(detail);
  const differenceClass = detail.operationalDifferenceAmount?.startsWith("-")
    ? "finance-negative-value"
    : "finance-positive-value";

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

      <section className="section finance-month-detail" aria-labelledby="finance-month-title">
        <div className="section-heading">
          <span className="eyebrow">Fechamento mensal verificável</span>
          <h1 id="finance-month-title">As contas de {formatMonth(detail.periodStart)}</h1>
          <p>
            Valores de {formatDate(detail.periodStart)} a {formatDate(detail.periodEnd)},
            publicados por {detail.publicBodyName}. Cada número abaixo aponta para o
            documento oficial que o sustenta.
          </p>
        </div>

        <section className={`finance-month-verdict finance-month-verdict-${detail.closureStatus}`} aria-labelledby="finance-verdict-title">
          <span>{status.label}</span>
          <h2 id="finance-verdict-title">{status.heading}</h2>
          <p>{status.explanation}</p>
        </section>

        <section aria-labelledby="finance-month-numbers-title">
          <div className="section-heading compact">
            <span className="eyebrow">Leitura rápida</span>
            <h2 id="finance-month-numbers-title">Quanto entrou e quanto saiu</h2>
            <p>O valor pago responde quanto saiu do caixa neste mês. Empenho e liquidação mostram etapas anteriores da mesma despesa.</p>
          </div>
          <dl className="finance-month-numbers">
            <div className="finance-month-income">
              <dt>Receita declarada <small>dinheiro informado como arrecadado</small></dt>
              <dd>{formatAmount(detail.revenueReportAmount)}</dd>
            </div>
            <div>
              <dt>Empenhado <small>valor reservado para despesas</small></dt>
              <dd>{formatAmount(detail.expenseCommittedAmount)}</dd>
            </div>
            <div>
              <dt>Liquidado <small>entrega ou serviço conferido</small></dt>
              <dd>{formatAmount(detail.expenseLiquidatedAmount)}</dd>
            </div>
            <div className="finance-month-paid">
              <dt>Pago <small>dinheiro que saiu do caixa</small></dt>
              <dd>{formatAmount(detail.expensePaidAmount)}</dd>
            </div>
            <div className={status.canShowDifference ? differenceClass : ""}>
              <dt>Diferença operacional <small>receita declarada menos pagamentos</small></dt>
              <dd>{status.canShowDifference ? formatAmount(detail.operationalDifferenceAmount) : "aguardando reconciliação"}</dd>
            </div>
          </dl>
        </section>

        <section className="finance-stage-section" aria-labelledby="finance-stage-title">
          <div className="section-heading compact">
            <span className="eyebrow">O caminho da despesa</span>
            <h2 id="finance-stage-title">Não some estas três etapas</h2>
            <p>Uma mesma despesa pode avançar pelos três momentos contábeis. Somá-los repetiria o mesmo dinheiro.</p>
          </div>
          <ol className="finance-stage-path">
            <li><span>1</span><div><strong>Empenhado</strong><p>A Prefeitura reservou o valor para uma obrigação.</p></div></li>
            <li><span>2</span><div><strong>Liquidado</strong><p>A entrega ou o serviço foi conferido.</p></div></li>
            <li><span>3</span><div><strong>Pago</strong><p>O dinheiro efetivamente saiu do caixa.</p></div></li>
          </ol>
        </section>

        {expenseLines.length > 0 ? (
          <section aria-labelledby="finance-month-lines-title">
            <div className="section-heading compact">
              <span className="eyebrow">Para onde foi o dinheiro</span>
              <h2 id="finance-month-lines-title">As 25 maiores linhas pagas no mês</h2>
              <p>
                Linhas contábeis do único relatório validado para esta competência,
                ordenadas pelo valor pago. Elas agrupam códigos de despesa: não são
                necessariamente pagamentos individuais nem um ranking de fornecedores.
              </p>
            </div>
            <details className="finance-details">
              <summary>Ver as linhas e os valores oficiais</summary>
              <div className="digest-grid">
                {expenseLines.map((line) => (
                  <ExpenseLineCard line={line} key={line.expenseLineId} />
                ))}
              </div>
            </details>
          </section>
        ) : null}

        <section className="finance-evidence-section" aria-labelledby="finance-evidence-title">
          <div className="section-heading compact">
            <span className="eyebrow">Provas do fechamento</span>
            <h2 id="finance-evidence-title">Documentos oficiais usados</h2>
            <p>
              {detail.revenueReportCount.toLocaleString("pt-BR")} relatório(s) de receita e {detail.expenseReportCount.toLocaleString("pt-BR")} relatório(s) de despesa. Se houver mais de uma versão, nenhuma diferença é apresentada até a reconciliação.
            </p>
          </div>
          <div className="finance-evidence-grid">
            {detail.revenueDocuments.map((document, index) => (
              <RevenueEvidence document={document} index={index} key={document.artifactSha256} />
            ))}
            {detail.expenseDocuments.map((document, index) => (
              <ExpenseEvidence document={document} index={index} key={document.artifactSha256} />
            ))}
          </div>
          {detail.revenueDocuments.length === 0 || detail.expenseDocuments.length === 0 ? (
            <p className="finance-missing-evidence" role="status">
              Ainda faltam documentos de {detail.revenueDocuments.length === 0 ? "receita" : "despesa"}. Ausência de documento não é tratada como valor zero.
            </p>
          ) : null}
        </section>

        <details className="finance-month-methodology">
          <summary>Como este fechamento foi calculado e validado</summary>
          <div>
            <p>{detail.coverageNote}</p>
            <p>
              Totais e diferença foram produzidos por código determinístico. Nenhum
              modelo de IA somou ou alterou valores financeiros.
            </p>
            <p>
              Metodologias: <code>{detail.calculationMethodology}</code> e <code>{detail.evidenceMethodology}</code>.
              Os hashes permitem conferir se os arquivos preservados permanecem iguais.
            </p>
            <p aria-label="Identificador auditável do fechamento">Fechamento: <code>{detail.closureId}</code></p>
          </div>
        </details>

        <p className="finance-month-hash-note">
          Exemplo de identificação preservada: {detail.revenueDocuments[0]
            ? shortHash(detail.revenueDocuments[0].artifactSha256)
            : detail.expenseDocuments[0]
              ? shortHash(detail.expenseDocuments[0].artifactSha256)
              : "nenhum documento disponível"}.
        </p>
      </section>
    </main>
  );
}
