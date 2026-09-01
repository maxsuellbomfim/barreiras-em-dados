"use client";

import { useEffect, useState } from "react";

import {
  buildMunicipalFinanceDocumentCoverage,
  municipalFinanceDocumentCoverageStatusLabel,
  parseMunicipalFinanceDocumentCoverageApiPayload,
  type MunicipalFinanceDocumentCoverageResult,
  type MunicipalFinanceDocumentCoverageStatus,
} from "../../lib/municipal-finance-document-coverage.mjs";

const LEGEND: readonly MunicipalFinanceDocumentCoverageStatus[] = [
  "preserved", "catalogued", "not_listed", "not_due",
];
const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  timeZone: "UTC",
});

function visualStatus(status: MunicipalFinanceDocumentCoverageStatus): string {
  if (status === "preserved") return "complete";
  if (status === "catalogued") return "expense_only";
  if (status === "not_listed") return "missing";
  return "not_due";
}

function cellLabel(status: MunicipalFinanceDocumentCoverageStatus): string {
  if (status === "preserved") return "Preservado";
  if (status === "catalogued") return "Catálogo";
  if (status === "not_listed") return "Não localizado";
  return "—";
}

function monthLabel(referenceMonth: number): string {
  return monthFormatter.format(new Date(Date.UTC(2026, referenceMonth - 1, 1)));
}

export default function FinanceMunicipalDocumentCoverage({
  initialResult,
}: Readonly<{ initialResult: MunicipalFinanceDocumentCoverageResult }>) {
  const [result, setResult] = useState(initialResult);
  const [isRefreshing, setIsRefreshing] = useState(initialResult.state === "unavailable");

  useEffect(() => {
    if (initialResult.state === "available") return;
    const controller = new AbortController();
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const response = await fetch("/api/municipal-finance-document-coverage", {
          cache: "no-store",
          signal: controller.signal,
        });
        const parsed = parseMunicipalFinanceDocumentCoverageApiPayload(await response.json());
        if (active && response.ok && parsed?.state === "available") setResult(parsed);
      } catch {
        // Sem as três famílias, nenhuma lacuna é classificada.
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
          <strong>{isRefreshing ? "Consultando balancetes, receita e despesa" : "Cobertura documental temporariamente indisponível"}</strong>
          <p>Sem resposta completa das três famílias, o portal não presume documentos ausentes.</p>
        </div>
      </div>
    );
  }

  const matrix = buildMunicipalFinanceDocumentCoverage(result.entries);
  if (!matrix) {
    return <div className="collection-unavailable" role="status"><div><strong>Calendário documental inconsistente</strong><p>Nenhuma lacuna foi presumida.</p></div></div>;
  }

  const count = (status: MunicipalFinanceDocumentCoverageStatus) => matrix.years.reduce(
    (total, year) => total + year.months.reduce(
      (monthTotal, month) => monthTotal + month.families.filter((family) => family.status === status).length,
      0,
    ),
    0,
  );
  const versionedPeriods = matrix.years.reduce(
    (total, year) => total + year.months.reduce(
      (monthTotal, month) => monthTotal + month.families.filter((family) => family.evidenceCount > 1).length,
      0,
    ),
    0,
  );

  return (
    <div className="finance-coverage-matrix finance-municipal-document-coverage">
      <div className="finance-coverage-summary" aria-label="Resumo dos documentos financeiros mensais">
        <div><strong>{count("preserved").toLocaleString("pt-BR")}</strong><span>PDFs preservados</span></div>
        <div><strong>{count("catalogued").toLocaleString("pt-BR")}</strong><span>encontrados; PDF pendente</span></div>
        <div><strong>{count("not_listed").toLocaleString("pt-BR")}</strong><span>competências vencidas não localizadas</span></div>
        <div><strong>{versionedPeriods.toLocaleString("pt-BR")}</strong><span>competências com versões</span></div>
      </div>
      <ul className="finance-coverage-legend" aria-label="Legenda da cobertura documental mensal">
        {LEGEND.map((status) => (
          <li key={status}>
            <span className={`finance-coverage-swatch finance-coverage-cell-${visualStatus(status)}`} />
            {municipalFinanceDocumentCoverageStatusLabel(status)}
          </li>
        ))}
      </ul>
      <div className="finance-municipal-document-years">
        {matrix.years.map((year, yearIndex) => (
          <details key={year.year} open={yearIndex === 0}>
            <summary>{year.year}</summary>
            <div className="finance-coverage-table-scroll finance-municipal-document-table" role="region" aria-label={`Documentos financeiros mensais de ${year.year}`} tabIndex={0}>
              <table>
                <caption>Balancetes, execução da receita e execução da despesa em {year.year}.</caption>
                <thead><tr><th scope="col">Mês</th>{matrix.families.map((family) => <th scope="col" key={family.resource}>{family.shortLabel}</th>)}</tr></thead>
                <tbody>
                  {year.months.map((month) => (
                    <tr key={month.referenceMonth}>
                      <th scope="row">{monthLabel(month.referenceMonth)}</th>
                      {month.families.map((family) => {
                        const statusLabel = municipalFinanceDocumentCoverageStatusLabel(family.status);
                        const versions = family.evidenceCount > 1 ? ` ${family.evidenceCount} versões encontradas; abre a versão preservada mais recente.` : "";
                        const explanation = `${family.shortLabel}, ${monthLabel(month.referenceMonth)} de ${year.year}: ${statusLabel}.${versions}`;
                        const className = `finance-coverage-cell finance-coverage-cell-${visualStatus(family.status)}`;
                        return (
                          <td key={family.resource}>
                            {family.entry ? (
                              <a className={className} href={family.entry.documentUrl} target="_blank" rel="noreferrer" aria-label={`${explanation} Abrir documento oficial.`} title={`${explanation} Abrir documento oficial.`}>
                                {family.evidenceCount > 1 ? `${family.evidenceCount} versões` : cellLabel(family.status)}
                              </a>
                            ) : (
                              <span className={className} aria-label={explanation} title={explanation}>{cellLabel(family.status)}</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </div>
      <p className="finance-coverage-method">
        “Não localizado no catálogo preservado consultado” significa apenas que o arquivo
        não apareceu após o prazo de trinta dias; não significa valor zero nem
        prova de omissão permanente. Quando há mais de uma versão para a mesma competência,
        nenhuma é somada e a célula informa a quantidade observada.
      </p>
    </div>
  );
}
