"use client";

import { useEffect, useState } from "react";

import {
  buildFiscalReportCoverageMatrix,
  fiscalReportCoverageStatusLabel,
  parseFiscalReportCoverageApiPayload,
  type FiscalReportCoverageResult,
  type FiscalReportCoverageStatus,
} from "../../lib/fiscal-report-coverage-matrix.mjs";

const LEGEND: readonly FiscalReportCoverageStatus[] = [
  "preserved", "catalogued", "unclassified", "not_due",
];

function visualStatus(status: FiscalReportCoverageStatus): string {
  if (status === "preserved") return "complete";
  if (status === "catalogued") return "expense_only";
  if (status === "unclassified") return "unclassified";
  return "not_due";
}

function cellLabel(status: FiscalReportCoverageStatus): string {
  if (status === "preserved") return "Preservado";
  if (status === "catalogued") return "Catálogo";
  if (status === "unclassified") return "Não classificado";
  return "—";
}

export default function FinanceFiscalReportCoverageMatrix({
  initialResult,
}: Readonly<{ initialResult: FiscalReportCoverageResult }>) {
  const [result, setResult] = useState(initialResult);
  const [isRefreshing, setIsRefreshing] = useState(initialResult.state === "unavailable");

  useEffect(() => {
    if (initialResult.state === "available") return;
    const controller = new AbortController();
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const response = await fetch("/api/fiscal-report-coverage", {
          cache: "no-store",
          signal: controller.signal,
        });
        const parsed = parseFiscalReportCoverageApiPayload(await response.json());
        if (active && response.ok && parsed?.state === "available") setResult(parsed);
      } catch {
        // Sem resposta das duas famílias, nenhum período é presumido.
      } finally {
        if (active) setIsRefreshing(false);
      }
    }
    void refresh();
    return () => {
      active = false;
      controller.abort();
    };
  }, [initialResult]);

  if (result.state === "unavailable") {
    return (
      <div className="collection-unavailable" role="status" aria-live="polite">
        <div>
          <strong>{isRefreshing ? "Consultando RREO e RGF" : "Cobertura fiscal temporariamente indisponível"}</strong>
          <p>Sem resposta das duas fontes, o portal não marca períodos como ausentes.</p>
        </div>
      </div>
    );
  }

  const matrix = buildFiscalReportCoverageMatrix(result.entries);
  if (!matrix) {
    return <div className="collection-unavailable" role="status"><div><strong>Calendário fiscal inconsistente</strong><p>Nenhuma falta foi presumida.</p></div></div>;
  }
  const count = (status: FiscalReportCoverageStatus) => matrix.years.reduce(
    (total, year) => total + year.periods.filter((period) => period.status === status).length,
    0,
  );

  return (
    <div className="finance-coverage-matrix finance-fiscal-report-coverage-matrix">
      <div className="finance-coverage-summary" aria-label="Resumo da cobertura de RREO e RGF">
        <div><strong>{count("preserved").toLocaleString("pt-BR")}</strong><span>períodos com PDF preservado no recorte</span></div>
        <div><strong>{count("catalogued").toLocaleString("pt-BR")}</strong><span>períodos encontrados; PDF pendente</span></div>
        <div><strong>{count("unclassified").toLocaleString("pt-BR")}</strong><span>períodos não classificados nesta consulta</span></div>
      </div>
      <ul className="finance-coverage-legend" aria-label="Legenda do calendário fiscal">
        {LEGEND.map((status) => (
          <li key={status}>
            <span className={`finance-coverage-swatch finance-coverage-cell-${visualStatus(status)}`} />
            {fiscalReportCoverageStatusLabel(status)}
          </li>
        ))}
      </ul>
      <div className="finance-coverage-table-scroll" role="region" aria-label="Calendário de RREO e RGF" tabIndex={0}>
        <table>
          <caption>RREO bimestral e RGF quadrimestral desde 2021, sem misturar os dois calendários.</caption>
          <thead>
            <tr><th scope="col" rowSpan={2}>Ano</th><th scope="colgroup" colSpan={6}>RREO</th><th scope="colgroup" colSpan={3}>RGF</th></tr>
            <tr>{matrix.columns.map((column) => <th scope="col" key={`${column.resource}-${column.referenceMonth}`}>{column.shortLabel}</th>)}</tr>
          </thead>
          <tbody>
            {matrix.years.map((year) => (
              <tr key={year.year}>
                <th scope="row">{year.year}</th>
                {year.periods.map((period) => {
                  const report = period.resource.toUpperCase();
                  const label = fiscalReportCoverageStatusLabel(period.status);
                  const explanation = `${report}, ${period.shortLabel} de ${year.year}: ${label}.`;
                  const className = `finance-coverage-cell finance-coverage-cell-${visualStatus(period.status)}`;
                  return (
                    <td key={`${period.resource}-${period.referenceMonth}`}>
                      {period.entry ? (
                        <a className={className} href={period.entry.documentUrl} target="_blank" rel="noreferrer" aria-label={`${explanation} Abrir documento oficial.`} title={`${explanation} Abrir documento oficial.`}>
                          {cellLabel(period.status)}
                        </a>
                      ) : (
                        <span className={className} aria-label={explanation} title={explanation}>{cellLabel(period.status)}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="finance-coverage-method">
        O calendário considera os prazos de trinta dias após cada período. Barreiras
        tem mais de 50 mil habitantes; por isso o RGF é acompanhado por quadrimestre.
        “Não classificado” indica que não recebemos um documento para o período
        nesta lista limitada a 200 registros por tipo de relatório. Isso não
        comprova ausência na fonte nem atraso na publicação. Os contadores medem
        períodos por tipo de relatório, não a quantidade total de PDFs.
        Consulte a <a href="https://www.siconfi.tesouro.gov.br/siconfi/pages/public/conteudo/conteudo.jsf?id=585" target="_blank" rel="noreferrer">regra no Siconfi</a>
        {" e a "}<a href="https://www.ibge.gov.br/cidades-e-estados/ba/barreiras.html" target="_blank" rel="noreferrer">população no IBGE</a>.
      </p>
    </div>
  );
}
