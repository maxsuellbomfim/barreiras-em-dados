import { formatBrlDecimal } from "../../lib/revenues";
import type { PublicPayrollMonth } from "../../lib/public-payroll.mjs";

const collectedAtFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatMonthTitle(value: string): string {
  const parsed = new Date(`${value}T12:00:00-03:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(parsed);
}

function formatCollectedAt(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : collectedAtFormatter.format(parsed);
}

export default function FinancePayrollHistory({
  months,
}: Readonly<{ months: readonly PublicPayrollMonth[] }>) {
  if (months.length === 0) return null;

  return (
    <details className="finance-payroll-history">
      <summary>
        <span>Ver meses anteriores da folha</span>
        <small>
          {months.length.toLocaleString("pt-BR")} mês
          {months.length === 1 ? "" : "es"} publicado
          {months.length === 1 ? "" : "s"}
        </small>
      </summary>
      <div className="finance-payroll-history-list">
        {months.map((month) => (
          <article
            className="finance-payroll-history-card"
            key={`${month.referenceMonth}-${month.artifactSha256}`}
          >
            <header>
              <div>
                <span className="finance-payroll-kicker">
                  {month.publicBodyName}
                </span>
                <h3>{formatMonthTitle(month.referenceMonth)}</h3>
              </div>
              <span className="finance-payroll-history-status">
                Mês validado por código
              </span>
            </header>
            <dl className="finance-payroll-history-values">
              <div>
                <dt>Proventos brutos</dt>
                <dd>{formatBrlDecimal(month.grossAmount)}</dd>
              </div>
              <div>
                <dt>Descontos</dt>
                <dd>{formatBrlDecimal(month.deductionAmount)}</dd>
              </div>
              <div>
                <dt>Líquido no relatório</dt>
                <dd>{formatBrlDecimal(month.netAmount)}</dd>
              </div>
            </dl>
            <p className="finance-payroll-history-note">
              {month.employeeCount.toLocaleString("pt-BR")} vínculos ·{" "}
              {month.subtotalCount.toLocaleString("pt-BR")} subtotais
              reconciliados. O líquido é bruto menos descontos no PDF; não é
              confirmação bancária.
            </p>
            <p className="act-evidence">
              <a href={month.sourceUrl} target="_blank" rel="noreferrer">
                Abrir PDF oficial deste mês →
              </a>{" "}
              · coletado em {formatCollectedAt(month.sourceRetrievedAt)} · hash{" "}
              {month.artifactSha256.slice(0, 12)}…
            </p>
          </article>
        ))}
      </div>
    </details>
  );
}
