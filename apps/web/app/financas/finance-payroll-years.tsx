import { formatBrlDecimal } from "../../lib/revenues";
import type { PublicPayrollYearSummary } from "../../lib/public-payroll.mjs";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "long",
  timeZone: "America/Bahia",
});

function coverageLabel(
  summary: PublicPayrollYearSummary,
  latestYear: number,
): string {
  if (summary.year === latestYear) {
    const month = String(summary.expectedMonthCount).padStart(2, "0");
    const periodEnd = monthFormatter.format(
      new Date(`${summary.year}-${month}-01T12:00:00-03:00`),
    );
    return summary.isComplete
      ? `janeiro a ${periodEnd} completos`
      : `${summary.publishedMonthCount} de ${summary.expectedMonthCount} meses até ${periodEnd}`;
  }
  return summary.isComplete
    ? "12 meses publicados"
    : `${summary.publishedMonthCount} de 12 meses publicados`;
}

export default function FinancePayrollYears({
  summaries,
}: Readonly<{ summaries: readonly PublicPayrollYearSummary[] }>) {
  if (summaries.length === 0) return null;
  const latest = summaries[0];

  return (
    <details className="finance-payroll-years">
      <summary>
        <span>Quanto a folha somou em cada ano</span>
        <small>
          {latest.year} até agora: {formatBrlDecimal(latest.grossAmount)} brutos
        </small>
      </summary>
      <div className="finance-payroll-years-body">
        <p>
          Soma determinística apenas das competências publicadas abaixo. Ano com
          mês ausente é identificado como parcial — o Barreiras 360 não converte
          documento não encontrado ou conflitante em valor zero.
        </p>
        <div className="finance-payroll-years-grid">
          {summaries.map((summary) => (
            <article key={summary.year}>
              <header>
                <h3>{summary.year}</h3>
                <span className={summary.isComplete ? "is-complete" : "is-partial"}>
                  {coverageLabel(summary, latest.year)}
                </span>
              </header>
              <dl>
                <div>
                  <dt>Bruto nos meses publicados</dt>
                  <dd>{formatBrlDecimal(summary.grossAmount)}</dd>
                </div>
                <div>
                  <dt>Descontos</dt>
                  <dd>{formatBrlDecimal(summary.deductionAmount)}</dd>
                </div>
                <div>
                  <dt>Líquido nos relatórios</dt>
                  <dd>{formatBrlDecimal(summary.netAmount)}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
        <small>
          “Líquido nos relatórios” é bruto menos descontos e não confirma a saída
          bancária. Os valores incluem os ciclos de 13º quando publicados
          separadamente no mês, sem duplicar a contagem de vínculos.
        </small>
      </div>
    </details>
  );
}
