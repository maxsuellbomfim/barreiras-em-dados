"use client";

import { useEffect, useState } from "react";

import type { PublicPayrollCoverageResult } from "../../lib/public-payroll.mjs";
import {
  buildPayrollCoverageMatrix,
  parsePayrollCoverageApiPayload,
  payrollCoverageStatusLabel,
  type PayrollCoverageMatrixStatus,
} from "../../lib/payroll-coverage-matrix.mjs";

const MONTHS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
] as const;
const LEGEND: readonly PayrollCoverageMatrixStatus[] = [
  "published", "processing_pending", "source_conflict", "document_not_found", "unclassified",
];

function visualStatus(status: PayrollCoverageMatrixStatus): string {
  if (status === "published") return "complete";
  if (status === "processing_pending") return "expense_only";
  if (status === "source_conflict") return "needs_review";
  if (status === "document_not_found") return "missing";
  if (status === "not_due") return "not_due";
  return "unclassified";
}

function cellLabel(status: PayrollCoverageMatrixStatus): string {
  if (status === "published") return "Publicado";
  if (status === "processing_pending") return "Validando";
  if (status === "source_conflict") return "Conflito";
  if (status === "document_not_found") return "Não localizado";
  if (status === "unclassified") return "Não classificado";
  return "—";
}

export default function FinancePayrollCoverageMatrix({
  initialResult,
}: Readonly<{ initialResult: PublicPayrollCoverageResult }>) {
  const [result, setResult] = useState(initialResult);
  const [isRefreshing, setIsRefreshing] = useState(initialResult.state === "unavailable");

  useEffect(() => {
    if (initialResult.state === "available") return;
    const controller = new AbortController();
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const response = await fetch("/api/payroll-coverage", {
          cache: "no-store",
          signal: controller.signal,
        });
        const parsed = parsePayrollCoverageApiPayload(await response.json());
        if (active && response.ok && parsed?.state === "available") setResult(parsed);
      } catch {
        // Nenhuma competência é presumida quando a fonte não responde.
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
          <strong>
            {isRefreshing ? "Consultando a cobertura da folha" : "Cobertura da folha temporariamente indisponível"}
          </strong>
          <p>A falta de resposta não significa folha ou gasto igual a zero.</p>
        </div>
      </div>
    );
  }

  const matrix = buildPayrollCoverageMatrix(result.rows);
  if (!matrix || matrix.years.length === 0) {
    return (
      <div className="collection-unavailable" role="status">
        <div><strong>Matriz da folha ainda indisponível</strong><p>Nenhuma competência foi presumida.</p></div>
      </div>
    );
  }
  const count = (status: string) => result.rows.filter((row) => row.coverageStatus === status).length;

  return (
    <div className="finance-coverage-matrix finance-payroll-coverage-matrix">
      <div className="finance-coverage-summary" aria-label="Resumo da cobertura mensal da folha">
        <div><strong>{count("published").toLocaleString("pt-BR")}</strong><span>meses publicados</span></div>
        <div><strong>{count("processing_pending").toLocaleString("pt-BR")}</strong><span>meses em validação</span></div>
        <div><strong>{count("document_not_found").toLocaleString("pt-BR")}</strong><span>documentos não localizados</span></div>
      </div>
      <ul className="finance-coverage-legend" aria-label="Legenda da matriz da folha">
        {LEGEND.map((status) => (
          <li key={status}>
            <span className={`finance-coverage-swatch finance-coverage-cell-${visualStatus(status)}`} />
            {payrollCoverageStatusLabel(status)}
          </li>
        ))}
      </ul>
      <div className="finance-coverage-table-scroll" role="region" aria-label="Cobertura mensal da folha" tabIndex={0}>
        <table>
          <caption>Folha regular e ciclos adicionais validados por competência desde 2021.</caption>
          <thead><tr><th scope="col">Ano</th>{MONTHS.map((month) => <th scope="col" key={month}>{month}</th>)}</tr></thead>
          <tbody>
            {matrix.years.map((year) => (
              <tr key={year.year}>
                <th scope="row">{year.year}</th>
                {year.months.map((month) => {
                  const label = payrollCoverageStatusLabel(month.status);
                  const explanation = `${MONTHS[month.month - 1]} de ${year.year}: ${label}. ${month.row?.coverageNote ?? ""}`.trim();
                  const className = `finance-coverage-cell finance-coverage-cell-${visualStatus(month.status)}`;
                  return (
                    <td key={month.month}>
                      {month.row?.sourceUrl ? (
                        <a className={className} href={month.row.sourceUrl} target="_blank" rel="noreferrer" aria-label={`${explanation} Abrir catálogo oficial.`} title={`${explanation} Abrir catálogo oficial.`}>
                          {cellLabel(month.status)}
                        </a>
                      ) : (
                        <span className={className} aria-label={explanation} title={explanation}>{cellLabel(month.status)}</span>
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
        A matriz cobre a folha agregada. Estagiários e terceirizados permanecem
        em cobertura separada e nenhum valor pessoal é publicado.
      </p>
    </div>
  );
}
