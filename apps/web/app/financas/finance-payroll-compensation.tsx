import type { PublicPayrollCompensationRow } from "../../lib/public-payroll.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

function shareLabel(part: number, total: number): string {
  if (total === 0) return "0,0%";
  return `${((part * 100) / total).toFixed(1).replace(".", ",")}%`;
}

export default function FinancePayrollCompensation({
  rows,
}: Readonly<{ rows: readonly PublicPayrollCompensationRow[] }>) {
  if (rows.length === 0) return null;
  const totalLinks = rows.reduce((sum, row) => sum + row.employeeCount, 0);
  const { averageGrossAmount, maximumGrossAmount } = rows[0];

  return (
    <details className="finance-payroll-compensation">
      <summary>
        <span>Em quais faixas estão os proventos brutos</span>
        <small>{totalLinks.toLocaleString("pt-BR")} vínculos regulares</small>
      </summary>
      <p className="finance-payroll-regimes-intro">
        Esta distribuição usa somente o valor bruto de cada linha da folha regular.
        Não soma 13º, não identifica pessoas e não representa salário-base: o bruto
        pode incluir vantagens e outros componentes informados pela Prefeitura.
      </p>
      <dl className="finance-payroll-compensation-summary">
        <div>
          <dt>Média bruta por vínculo</dt>
          <dd>{formatBrlDecimal(averageGrossAmount)}</dd>
        </div>
        <div>
          <dt>Maior bruto em uma linha</dt>
          <dd>{formatBrlDecimal(maximumGrossAmount)}</dd>
        </div>
      </dl>
      <div className="finance-payroll-compensation-list">
        {rows.map((row) => (
          <article key={row.bandCode}>
            <div>
              <strong>{row.bandLabel}</strong>
              <span>
                {row.employeeCount.toLocaleString("pt-BR")} vínculos ·{" "}
                {shareLabel(row.employeeCount, totalLinks)}
              </span>
            </div>
            <progress value={row.employeeCount} max={totalLinks}>
              {shareLabel(row.employeeCount, totalLinks)}
            </progress>
          </article>
        ))}
      </div>
      <p className="finance-details-note">
        Contagem, média, maior valor e faixas são calculados por código e só são
        publicados quando todas as linhas fecham com o total oficial do PDF.
      </p>
    </details>
  );
}
