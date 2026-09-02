"use client";

import { useEffect, useState } from "react";

import type { PublicFinanceCoverageResult } from "../../lib/finance-coverage";
import {
  buildFinanceCoverageMatrix,
  financeCoverageStatusLabel,
  parseFinanceCoverageApiPayload,
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
  "not_due",
];

function cellLabel(status: FinanceCoverageMatrixStatus): string {
  if (status === "complete") return "Completo";
  if (status === "revenue_only") return "Receita";
  if (status === "expense_only") return "Despesa";
  if (status === "needs_review") return "Revisar";
  if (status === "missing") return "Sem relatório";
  if (status === "unclassified") return "Não classificado";
  return "Ainda não exigível";
}

function currentPeriodInBarreiras(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Bahia",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  return `${year}-${month}`;
}

export default function FinanceCoverageMatrix({
  initialResult,
}: Readonly<{ initialResult: PublicFinanceCoverageResult }>) {
  const [result, setResult] = useState(initialResult);
  const [isRefreshing, setIsRefreshing] = useState(initialResult.state === "unavailable");

  useEffect(() => {
    if (initialResult.state === "available") return;
    const controller = new AbortController();
    let active = true;
    async function refresh(): Promise<void> {
      try {
        const response = await fetch("/api/finance-coverage", {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload: unknown = await response.json();
        const parsed = parseFinanceCoverageApiPayload(payload);
        if (active && response.ok && parsed?.state === "available") {
          setResult(parsed);
        }
      } catch {
        // O estado público abaixo preserva a indisponibilidade sem fabricar dados.
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
              ? "Consultando a cobertura financeira"
              : "Cobertura financeira temporariamente indisponível"}
          </strong>
          <p>
            A página não recebeu a classificação mensal nesta tentativa. Isso
            não significa ausência de relatórios nem valores iguais a zero.
          </p>
        </div>
      </div>
    );
  }

  const rows = result.rows;
  const matrix = buildFinanceCoverageMatrix(
    rows,
    2021,
    currentPeriodInBarreiras(),
  );
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

  const displayedMonths = matrix.bodies.flatMap((body) =>
    body.years.flatMap((year) => year.months.filter((month) => month.row)),
  );
  const comparableMonths = displayedMonths.filter(
    (month) => month.status === "complete",
  ).length;
  const missingMonths = displayedMonths.filter(
    (month) => month.status === "missing",
  ).length;

  return (
    <div className="finance-coverage-matrix">
      <div className="finance-coverage-summary" aria-label="Resumo da cobertura financeira">
        <div><strong>{comparableMonths.toLocaleString("pt-BR")}</strong><span>meses comparáveis</span></div>
        <div><strong>{missingMonths.toLocaleString("pt-BR")}</strong><span>meses sem relatório</span></div>
        <div><strong>{rows.length.toLocaleString("pt-BR")}</strong><span>meses acompanhados</span></div>
      </div>
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
                      const evidence = month.status === "not_due"
                        ? month.row
                          ? "A competência ainda está em andamento; a ausência de relatório validado não é tratada como atraso nem valor zero."
                          : "Competência futura, ainda fora do período acompanhado."
                        : month.row
                          ? `${month.row.coverageNote} Relatórios de receita: ${month.row.revenueReportCount}. Relatórios de despesa: ${month.row.expenseReportCount}.`
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
        precisa de diagnóstico. “Competência em andamento ou futura” não é
        contada como lacuna. Nenhum desses estados significa valor zero.{" "}
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
