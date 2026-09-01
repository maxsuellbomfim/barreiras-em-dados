import type { PublicFinanceCoverageRow } from "../../lib/finance-coverage";
import {
  buildFinanceCoverageMatrix,
  financeCoverageStatusLabel,
  type FinanceCoverageMatrixStatus,
} from "../../lib/finance-coverage-matrix.mjs";

const MONTHS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
] as const;

const LEGEND_STATUSES: readonly FinanceCoverageMatrixStatus[] = [
  "complete",
  "revenue_only",
  "expense_only",
  "needs_review",
  "missing",
  "unclassified",
];

function cellLabel(status: FinanceCoverageMatrixStatus): string {
  if (status === "complete") return "Completo";
  if (status === "revenue_only") return "Receita";
  if (status === "expense_only") return "Despesa";
  if (status === "needs_review") return "Revisar";
  if (status === "missing") return "Sem relatório";
  if (status === "unclassified") return "Não classificado";
  return "—";
}

export default function FinanceCoverageMatrix({
  rows,
}: Readonly<{ rows: readonly PublicFinanceCoverageRow[] }>) {
  const matrix = buildFinanceCoverageMatrix(rows);
  if (!matrix || matrix.bodies.length === 0) {
    return (
      <div className="collection-unavailable" role="status">
        <div>
          <strong>Matriz de cobertura ainda indisponível</strong>
          <p>
            A lista recebida não permite classificar as competências com
            segurança. Nenhuma lacuna foi convertida em valor zero.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="finance-coverage-matrix">
      <ul className="finance-coverage-legend" aria-label="Legenda da matriz">
        {LEGEND_STATUSES.map((status) => (
          <li key={status}>
            <span className={`finance-coverage-swatch finance-coverage-cell-${status}`} />
            {financeCoverageStatusLabel(status)}
          </li>
        ))}
      </ul>

      {matrix.bodies.map((body) => (
        <section className="finance-coverage-body" key={body.publicBodyName}>
          <h3>{body.publicBodyName}</h3>
          <div
            className="finance-coverage-table-scroll"
            role="region"
            aria-label={`Cobertura mensal de ${body.publicBodyName}`}
            tabIndex={0}
          >
            <table>
              <caption>
                Receitas e despesas municipais validadas, de 2021 a {matrix.latestPeriod?.slice(0, 4)}.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Ano</th>
                  {MONTHS.map((month) => <th scope="col" key={month}>{month}</th>)}
                </tr>
              </thead>
              <tbody>
                {body.years.map((year) => (
                  <tr key={year.year}>
                    <th scope="row">{year.year}</th>
                    {year.months.map((month) => {
                      const statusLabel = financeCoverageStatusLabel(month.status);
                      const evidence = month.row
                        ? `${month.row.coverageNote} Relatórios de receita: ${month.row.revenueReportCount}. Relatórios de despesa: ${month.row.expenseReportCount}.`
                        : month.status === "not_due"
                          ? "Competência posterior ao último mês acompanhado pela projeção."
                          : "A resposta pública não trouxe uma classificação para esta competência.";
                      const explanation = `${MONTHS[month.month - 1]} de ${year.year}: ${statusLabel}. ${evidence}`;
                      return (
                        <td key={month.month}>
                          <span
                            className={`finance-coverage-cell finance-coverage-cell-${month.status}`}
                            aria-label={explanation}
                            title={explanation}
                          >
                            {cellLabel(month.status)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <p className="finance-coverage-method">
        “Sem relatório validado” é o resultado da busca mensal na projeção;
        “não classificado” indica que a competência não veio na resposta e
        precisa de diagnóstico. Nenhum dos dois estados significa valor zero.{" "}
        <a href="#document-title">Conferir os documentos publicados</a> ou{" "}
        <a
          href="https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/"
          target="_blank"
          rel="noreferrer"
        >
          consultar a fonte oficial ↗
        </a>.
      </p>
    </div>
  );
}
