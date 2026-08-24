import {
  summarizeAdminSiconfiReconciliation,
  type AdminSiconfiReconciliationMetric,
  type AdminSiconfiReconciliationYear,
} from "./siconfi-reconciliation.mjs";

export type AdminSiconfiReconciliationState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{
      kind: "ready";
      years: readonly AdminSiconfiReconciliationYear[];
    }>;

const MONTH_NAMES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

const STATUS_PRIORITY = {
  source_difference: 0,
  incomplete_months: 1,
  matched_exact: 2,
} as const;

function metricLabel(metric: AdminSiconfiReconciliationMetric): string {
  if (metric.metricKey === "expense_committed") return "Empenhado";
  if (metric.metricKey === "expense_liquidated") return "Liquidado";
  return "Pago";
}

function statusLabel(metric: AdminSiconfiReconciliationMetric): string {
  if (metric.reconciliationStatus === "matched_exact") return "Confere exatamente";
  if (metric.reconciliationStatus === "source_difference") return "Diferença entre fontes";
  return "Cobertura mensal incompleta";
}

function formatDecimalAmount(value: string | null): string {
  if (value === null || !/^-?\d+(?:\.\d{1,2})?$/.test(value)) return "—";
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `R$ ${negative ? "-" : ""}${grouped},${fraction.padEnd(2, "0")}`;
}

function missingMonthNames(months: readonly number[]): string {
  return months.map((month) => MONTH_NAMES[month - 1]).join(", ");
}

export function SiconfiReconciliationPanel({
  state,
}: Readonly<{ state: AdminSiconfiReconciliationState }>) {
  const years = state.kind === "ready" ? state.years : [];
  const summary = summarizeAdminSiconfiReconciliation(years);

  return (
    <section
      className="siconfi-reconciliation-panel"
      aria-labelledby="siconfi-reconciliation-title"
    >
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Conferência entre fontes oficiais</span>
        <h2 id="siconfi-reconciliation-title">DCA anual × 12 fechamentos mensais</h2>
        <p>
          O banco compara, com decimal exato, os totais empenhado, liquidado e
          pago. Diferença entre fontes não é prova de irregularidade: é uma
          divergência que precisa permanecer visível e explicada.
        </p>
      </div>

      {state.kind === "loading" ? (
        <p aria-live="polite">Conferindo os exercícios do SICONFI…</p>
      ) : null}
      {state.kind === "error" ? (
        <p className="status-error" role="alert">
          A conferência anual não pôde ser carregada: {state.message}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        years.length === 0 ? (
          <div className="empty-state">Nenhum exercício anual disponível para conferência.</div>
        ) : (
          <>
            <dl
              className="siconfi-reconciliation-summary"
              aria-label="Resumo da conferência anual e mensal"
            >
              <div><dt>Exercícios</dt><dd>{summary.years}</dd></div>
              <div><dt>Conferem</dt><dd>{summary.exactMatches}</dd></div>
              <div><dt>Com diferença</dt><dd>{summary.sourceDifferences}</dd></div>
              <div><dt>Incompletos</dt><dd>{summary.incompleteMetrics}</dd></div>
            </dl>
            <div className="siconfi-reconciliation-years">
              {years.map((year) => {
                const orderedMetrics = [...year.metrics].sort(
                  (left, right) =>
                    STATUS_PRIORITY[left.reconciliationStatus] -
                    STATUS_PRIORITY[right.reconciliationStatus],
                );
                const requiresAttention = orderedMetrics.some(
                  (metric) => metric.reconciliationStatus !== "matched_exact",
                );
                return (
                  <details key={year.fiscalYear} open={requiresAttention}>
                    <summary>
                      Exercício {year.fiscalYear}
                      <span>{requiresAttention ? "verificar" : "todos conferem"}</span>
                    </summary>
                    <div className="siconfi-reconciliation-metrics">
                      {orderedMetrics.map((metric) => (
                        <article key={metric.metricKey}>
                          <div className="card-top">
                            <h3>{metricLabel(metric)}</h3>
                            <span className={`badge siconfi-${metric.reconciliationStatus}`}>
                              {statusLabel(metric)}
                            </span>
                          </div>
                          <dl>
                            <div><dt>DCA anual</dt><dd>{formatDecimalAmount(metric.annualAmount)}</dd></div>
                            <div><dt>Soma dos 12 meses</dt><dd>{formatDecimalAmount(metric.monthlySumAmount)}</dd></div>
                            <div><dt>Diferença</dt><dd>{formatDecimalAmount(metric.differenceAmount)}</dd></div>
                          </dl>
                          {metric.missingMonths.length > 0 ? (
                            <p className="siconfi-missing-months">
                              Meses ausentes: {missingMonthNames(metric.missingMonths)}.
                            </p>
                          ) : null}
                          <p className="meta">{metric.reconciliationNote}</p>
                        </article>
                      ))}
                    </div>
                  </details>
                );
              })}
            </div>
          </>
        )
      ) : null}
    </section>
  );
}
