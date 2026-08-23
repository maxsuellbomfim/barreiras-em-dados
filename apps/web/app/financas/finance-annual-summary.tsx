import type { AnnualFinanceSummary } from "../../lib/annual-finance-summary.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatMonth(periodStart: string): string {
  return monthFormatter.format(new Date(`${periodStart}T12:00:00-03:00`));
}

function differenceClass(value: string): string {
  return value.startsWith("-") ? "finance-negative-value" : "finance-positive-value";
}

export function FinanceAnnualSummary({
  summaries,
}: Readonly<{ summaries: readonly AnnualFinanceSummary[] }>) {
  if (summaries.length === 0) return null;

  return (
    <section className="finance-annual-section" aria-labelledby="finance-annual-title">
      <div className="section-heading compact">
        <span className="eyebrow">Visão por ano</span>
        <h2 id="finance-annual-title">O que os meses já publicados somam</h2>
        <p>
          Somamos somente meses reconciliados. Leia a cobertura antes dos valores e
          não compare anos com coberturas diferentes como se fossem períodos iguais.
        </p>
      </div>
      <ol className="finance-annual-list">
        {summaries.map((summary) => (
          <li key={summary.fiscalYear}>
            <header>
              <div>
                <span>{summary.isFullCalendarYear ? "Ano completo" : "Recorte parcial"}</span>
                <h3>{summary.fiscalYear}</h3>
              </div>
              <p>
                <strong>{summary.comparableMonthCount}</strong> meses reconciliados
                <small>{formatMonth(summary.firstPeriodStart)} a {formatMonth(summary.lastPeriodStart)}</small>
              </p>
            </header>
            <dl>
              <div className="finance-positive-value">
                <dt>Receita declarada</dt>
                <dd>{formatBrlDecimal(summary.revenueAmount)}</dd>
              </div>
              <div className="finance-negative-value">
                <dt>Pagamentos</dt>
                <dd>{formatBrlDecimal(summary.paidAmount)}</dd>
              </div>
              <div className={differenceClass(summary.operationalDifferenceAmount)}>
                <dt>Diferença operacional</dt>
                <dd>{formatBrlDecimal(summary.operationalDifferenceAmount)}</dd>
              </div>
            </dl>
            <a className="finance-annual-link" href={`/financas/ano/${summary.fiscalYear}`}>
              Ver {summary.fiscalYear} mês a mês →
            </a>
          </li>
        ))}
      </ol>
      <p className="finance-annual-method">
        Totais calculados em centavos por código determinístico. Nenhuma IA calculou
        ou alterou valores. A diferença operacional não é saldo bancário nem superávit.
      </p>
    </section>
  );
}
