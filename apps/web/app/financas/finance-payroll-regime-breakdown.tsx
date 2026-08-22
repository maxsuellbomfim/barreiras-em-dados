import type { PublicPayrollRegimeRow } from "../../lib/public-payroll.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

function cents(value: string): bigint {
  const [whole, fraction] = value.split(".");
  return BigInt(whole) * BigInt(100) + BigInt(fraction);
}

function shareLabel(part: string, total: string): string {
  const totalCents = cents(total);
  if (totalCents === BigInt(0)) return "0,0%";
  const tenths =
    (cents(part) * BigInt(1000) + totalCents / BigInt(2)) / totalCents;
  return `${tenths / BigInt(10)},${tenths % BigInt(10)}%`;
}

export default function FinancePayrollRegimeBreakdown({
  rows,
  grossTotal,
}: Readonly<{
  rows: readonly PublicPayrollRegimeRow[];
  grossTotal: string;
}>) {
  if (rows.length === 0) return null;
  return (
    <details className="finance-payroll-regimes">
      <summary>
        <span>Como a folha se divide por vínculo</span>
        <small>{rows.length.toLocaleString("pt-BR")} categorias oficiais</small>
      </summary>
      <p className="finance-payroll-regimes-intro">
        “Vínculo” é a classificação escrita no PDF da Prefeitura. A contagem
        representa relações funcionais e não representa necessariamente uma pessoa única.
        Nenhum nome, matrícula ou desconto individual é publicado aqui.
      </p>
      <div className="finance-payroll-regimes-list">
        {rows.map((row) => (
          <article key={row.regimeCode}>
            <header>
              <h4>{row.regimeLabel}</h4>
              <strong>{shareLabel(row.grossAmount, grossTotal)} do bruto</strong>
            </header>
            <dl>
              <div>
                <dt>Vínculos na folha regular</dt>
                <dd>{row.employeeCount.toLocaleString("pt-BR")}</dd>
              </div>
              <div>
                <dt>Proventos brutos</dt>
                <dd>{formatBrlDecimal(row.grossAmount)}</dd>
              </div>
              <div>
                <dt>Descontos</dt>
                <dd>{formatBrlDecimal(row.deductionAmount)}</dd>
              </div>
              <div>
                <dt>Líquido no relatório</dt>
                <dd>{formatBrlDecimal(row.netAmount)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
      <p className="finance-details-note">
        Os grupos fecham centavo a centavo com o total mensal acima. Percentuais e
        somas são calculados por código determinístico, sem IA.
      </p>
    </details>
  );
}
