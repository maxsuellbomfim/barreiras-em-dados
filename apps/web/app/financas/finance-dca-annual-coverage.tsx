import type { PublicSiconfiAnnualYear } from "../../lib/siconfi-annual-totals";
import {
  buildDcaAnnualCoverage,
  dcaAnnualCoverageStatusLabel,
  type DcaAnnualCoverageStatus,
} from "../../lib/dca-annual-coverage.mjs";

function visualStatus(status: DcaAnnualCoverageStatus): string {
  if (status === "published") return "complete";
  if (status === "not_found") return "missing";
  return "not_due";
}

export function FinanceDcaAnnualCoverage({
  years,
}: Readonly<{ years: readonly PublicSiconfiAnnualYear[] }>) {
  const coverage = buildDcaAnnualCoverage(years, { yearFrom: 2021 });
  if (!coverage) {
    return (
      <div className="collection-unavailable" role="status">
        <div>
          <strong>Cobertura anual inconsistente</strong>
          <p>Nenhum exercício ausente foi convertido em zero.</p>
        </div>
      </div>
    );
  }

  const published = coverage.filter((item) => item.status === "published").length;
  const notFound = coverage.filter((item) => item.status === "not_found").length;

  return (
    <div className="finance-coverage-matrix finance-dca-annual-coverage">
      <div className="finance-coverage-summary" aria-label="Resumo da cobertura anual da DCA">
        <div><strong>{published}</strong><span>exercícios publicados</span></div>
        <div><strong>{notFound}</strong><span>declarações não localizadas</span></div>
      </div>
      <div className="finance-coverage-table-scroll" role="region" aria-label="Cobertura anual da DCA" tabIndex={0}>
        <table>
          <caption>Declarações das Contas Anuais localizadas no SICONFI desde 2021.</caption>
          <thead><tr><th scope="col">Exercício</th><th scope="col">Situação na consulta</th><th scope="col">Evidência</th></tr></thead>
          <tbody>
            {coverage.map((item) => {
              const label = dcaAnnualCoverageStatusLabel(item.status);
              const className = `finance-coverage-cell finance-coverage-cell-${visualStatus(item.status)}`;
              return (
                <tr key={item.fiscalYear}>
                  <th scope="row">{item.fiscalYear}</th>
                  <td><span className={className}>{label}</span></td>
                  <td>
                    {item.sourceUrl ? (
                      <a href={item.sourceUrl} target="_blank" rel="noreferrer">Abrir declaração oficial →</a>
                    ) : item.status === "in_progress" ? (
                      <span>O ano ainda não terminou</span>
                    ) : (
                      <span>Sem documento na resposta consultada</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="finance-coverage-method">
        “Não localizada” significa somente que a DCA não apareceu na resposta
        oficial consultada. Não significa valor zero, ausência de movimentação
        financeira ou conclusão sobre a regularidade das contas.
      </p>
    </div>
  );
}
