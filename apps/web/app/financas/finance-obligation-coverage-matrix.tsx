"use client";

import { useEffect, useState } from "react";

import type { PublicObligationCoverageResult } from "../../lib/public-obligations.mjs";
import {
  buildObligationCoverageMatrix,
  obligationCoverageStatusLabel,
  parseObligationCoverageApiPayload,
  type ObligationCoverageMatrixStatus,
} from "../../lib/obligation-coverage-matrix.mjs";

const MONTHS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
] as const;

const LEGEND: readonly ObligationCoverageMatrixStatus[] = [
  "published",
  "section_absent",
  "section_incomplete",
  "source_conflict",
  "document_not_found",
  "document_not_confirmed",
  "unclassified",
];

function visualStatus(status: ObligationCoverageMatrixStatus): string {
  if (status === "published") return "complete";
  if (status === "section_absent") return "revenue_only";
  if (status === "section_incomplete" || status === "source_conflict") return "needs_review";
  if (status === "document_not_found") return "missing";
  if (status === "not_due") return "not_due";
  return "unclassified";
}

function cellLabel(status: ObligationCoverageMatrixStatus): string {
  if (status === "published") return "Publicado";
  if (status === "section_absent") return "Sem seção";
  if (status === "section_incomplete") return "Incompleta";
  if (status === "source_conflict") return "Divergência";
  if (status === "document_not_found") return "Não localizado";
  if (status === "document_not_confirmed") return "Não confirmado";
  if (status === "unclassified") return "Não classificado";
  return "—";
}

export default function FinanceObligationCoverageMatrix({
  initialResult,
}: Readonly<{ initialResult: PublicObligationCoverageResult }>) {
  const [result, setResult] = useState(initialResult);
  const [isRefreshing, setIsRefreshing] = useState(initialResult.state === "unavailable");

  useEffect(() => {
    if (initialResult.state === "available") return;
    const controller = new AbortController();
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const response = await fetch("/api/obligation-coverage", {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload: unknown = await response.json();
        const parsed = parseObligationCoverageApiPayload(payload);
        if (active && response.ok && parsed?.state === "available") setResult(parsed);
      } catch {
        // A indisponibilidade continua explícita; nenhum mês é fabricado.
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
            {isRefreshing
              ? "Consultando a cobertura de restos a pagar"
              : "Cobertura de restos a pagar temporariamente indisponível"}
          </strong>
          <p>
            A classificação mensal não foi recebida nesta tentativa. Isso não
            significa dívida, pagamento ou saldo igual a zero.
          </p>
        </div>
      </div>
    );
  }

  const matrix = buildObligationCoverageMatrix(result.rows);
  if (!matrix || matrix.years.length === 0) {
    return (
      <div className="collection-unavailable" role="status">
        <div>
          <strong>Matriz de restos a pagar ainda indisponível</strong>
          <p>Nenhuma competência foi presumida a partir de uma resposta vazia.</p>
        </div>
      </div>
    );
  }

  const published = result.rows.filter((row) => row.coverageStatus === "published").length;
  const sourceConflicts = result.rows.filter((row) => row.coverageStatus === "source_conflict").length;
  const absentDocuments = result.rows.filter((row) =>
    row.coverageStatus === "document_not_found" ||
    row.coverageStatus === "document_not_confirmed",
  ).length;

  return (
    <div className="finance-coverage-matrix finance-obligation-coverage-matrix">
      <div className="finance-coverage-summary" aria-label="Resumo da cobertura de restos a pagar">
        <div><strong>{published.toLocaleString("pt-BR")}</strong><span>meses com valor publicado</span></div>
        <div><strong>{sourceConflicts.toLocaleString("pt-BR")}</strong><span>divergências entre fontes</span></div>
        <div><strong>{absentDocuments.toLocaleString("pt-BR")}</strong><span>documentos não confirmados</span></div>
      </div>
      <ul className="finance-coverage-legend" aria-label="Legenda da matriz de restos a pagar">
        {LEGEND.map((status) => (
          <li key={status}>
            <span className={`finance-coverage-swatch finance-coverage-cell-${visualStatus(status)}`} />
            {obligationCoverageStatusLabel(status)}
          </li>
        ))}
      </ul>
      <div
        className="finance-coverage-table-scroll"
        role="region"
        aria-label="Cobertura mensal de restos a pagar"
        tabIndex={0}
      >
        <table>
          <caption>
            Situação documental de cada competência desde 2021. A matriz não informa o saldo da dívida.
          </caption>
          <thead>
            <tr>
              <th scope="col">Ano</th>
              {MONTHS.map((month) => <th scope="col" key={month}>{month}</th>)}
            </tr>
          </thead>
          <tbody>
            {matrix.years.map((year) => (
              <tr key={year.year}>
                <th scope="row">{year.year}</th>
                {year.months.map((month) => {
                  const label = obligationCoverageStatusLabel(month.status);
                  const explanation = `${MONTHS[month.month - 1]} de ${year.year}: ${label}.`;
                  const className = `finance-coverage-cell finance-coverage-cell-${visualStatus(month.status)}`;
                  return (
                    <td key={month.month}>
                      {month.row?.sourceUrl ? (
                        <a
                          aria-label={`${explanation} Abrir evidência oficial.`}
                          className={className}
                          href={month.row.sourceUrl}
                          rel="noreferrer"
                          target="_blank"
                          title={`${explanation} Abrir evidência oficial.`}
                        >
                          {cellLabel(month.status)}
                        </a>
                      ) : (
                        <span className={className} aria-label={explanation} title={explanation}>
                          {cellLabel(month.status)}
                        </span>
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
        “Valor publicado” indica que o total mensal passou pelas validações da
        projeção. Os demais estados explicam por que nenhum valor foi mostrado;
        divergência documental não é prova de irregularidade.
      </p>
    </div>
  );
}
