"use client";

import { formatBackfillProgress } from "./collection-backfill.mjs";

export type CollectionHealthItem = Readonly<{
  endpoint_id: string;
  source_slug: string;
  source_name: string;
  source_status: "active" | "degraded" | "paused" | "retired";
  endpoint_slug: string;
  endpoint_kind: string;
  endpoint_enabled: boolean;
  latest_partition_key: string | null;
  latest_partition_status:
    | "complete"
    | "empty"
    | "partial"
    | "failed"
    | "blocked"
    | null;
  latest_period_start: string | null;
  latest_period_end: string | null;
  latest_expected_records: number | null;
  latest_observed_records: number | null;
  latest_attempted_at: string | null;
  latest_completed_at: string | null;
  latest_run_status: string | null;
  latest_collector_version: string | null;
  complete_partitions: number;
  empty_partitions: number;
  partial_partitions: number;
  failed_partitions: number;
  blocked_partitions: number;
  unresolved_failures: number;
  latest_failure_status: string | null;
  latest_failure_type: string | null;
  latest_failure_detail: string | null;
  latest_failure_attempt_count: number | null;
  latest_failure_retryable: boolean | null;
  latest_failure_next_retry_at: string | null;
  latest_failure_at: string | null;
  backfill_horizon: string | null;
  continuous_coverage_start: string | null;
  continuous_coverage_end: string | null;
  next_backfill_start: string | null;
  next_backfill_end: string | null;
  backfill_classified_days: number | null;
  backfill_total_days: number | null;
  backfill_progress_percent: number | null;
  methodology_version: string;
}>;

export type CollectionHealthState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly CollectionHealthItem[] }>;

function normalize(value: string): string {
  return value
    .toLocaleLowerCase("pt-BR")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function healthLabel(
  status: CollectionHealthItem["latest_partition_status"],
): string {
  if (status === "complete") return "Cobertura completa";
  if (status === "empty") return "Vazio confirmado";
  if (status === "partial") return "Cobertura parcial";
  if (status === "failed") return "Coleta falhou";
  if (status === "blocked") return "Coleta bloqueada";
  return "Ainda sem execução controlada";
}

function healthTone(item: CollectionHealthItem): string {
  if (item.latest_partition_status === null) return "unknown";
  if (
    item.latest_partition_status === "failed" ||
    item.latest_partition_status === "blocked"
  ) {
    return "failed";
  }
  if (
    item.latest_partition_status === "partial" ||
    item.unresolved_failures > 0 ||
    item.source_status === "degraded"
  ) {
    return "attention";
  }
  return "healthy";
}

function formatPeriod(item: CollectionHealthItem): string {
  if (!item.latest_period_start || !item.latest_period_end) return "—";
  const start = new Date(`${item.latest_period_start}T12:00:00-03:00`);
  const end = new Date(`${item.latest_period_end}T12:00:00-03:00`);
  const formatter = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Bahia",
  });
  const startLabel = formatter.format(start);
  const endLabel = formatter.format(end);
  return startLabel === endLabel ? startLabel : `${startLabel} a ${endLabel}`;
}

function formatLag(item: CollectionHealthItem): string {
  if (!item.latest_period_end || !item.latest_attempted_at) return "Sem período comparável";
  const periodEnd = new Date(`${item.latest_period_end}T23:59:59-03:00`).getTime();
  const attemptedAt = new Date(item.latest_attempted_at).getTime();
  if (!Number.isFinite(periodEnd) || !Number.isFinite(attemptedAt)) {
    return "Sem período comparável";
  }
  const days = Math.max(0, Math.floor((attemptedAt - periodEnd) / 86_400_000));
  if (days === 0) return "Sem atraso mensurável";
  return `${days.toLocaleString("pt-BR")} dia${days === 1 ? "" : "s"} após o fim do período`;
}

export function CollectionHealth({
  state,
  search,
  onSearchChange,
  onReload,
}: Readonly<{
  state: CollectionHealthState;
  search: string;
  onSearchChange: (value: string) => void;
  onReload: () => void;
}>) {
  const items = state.kind === "ready" ? state.items : [];
  const term = normalize(search.trim());
  const visible = items.filter((item) =>
    normalize(
      [
        item.source_name,
        item.source_slug,
        item.endpoint_slug,
        item.endpoint_kind,
        item.latest_failure_type ?? "",
        item.latest_failure_detail ?? "",
      ].join(" "),
    ).includes(term),
  );
  const withoutCoverage = items.filter(
    (item) => item.latest_partition_status === null,
  ).length;
  const requiringAttention = items.filter((item) => {
    const tone = healthTone(item);
    return tone === "failed" || tone === "attention";
  }).length;
  const openFailures = items.reduce(
    (total, item) => total + item.unresolved_failures,
    0,
  );

  return (
    <section aria-labelledby="collection-health-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Operação e cobertura</span>
        <h2 id="collection-health-title">Saúde das fontes</h2>
        <p>
          Diagnóstico por endpoint oficial. “Ainda sem execução controlada” não
          significa que a fonte não tenha dados: significa que o coletor ainda
          não registrou uma partição verificável para ela.
        </p>
      </div>

      {state.kind === "loading" ? (
        <p aria-live="polite">Carregando saúde das fontes…</p>
      ) : null}
      {state.kind === "error" ? (
        <p className="status-error" role="alert">
          O diagnóstico das fontes não pôde ser carregado: {state.message}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        <>
          <dl
            className="source-health-stats"
            aria-label="Resumo da saúde das fontes"
          >
            <div>
              <dt>Endpoints monitorados</dt>
              <dd>{items.length.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Sem cobertura registrada</dt>
              <dd>{withoutCoverage.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Requerem atenção</dt>
              <dd>{requiringAttention.toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Falhas não resolvidas</dt>
              <dd>{openFailures.toLocaleString("pt-BR")}</dd>
            </div>
          </dl>
          <div className="toolbar">
            <input
              type="search"
              aria-label="Buscar fonte ou endpoint"
              placeholder="Buscar fonte, endpoint ou falha…"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
            />
            <button type="button" className="secondary" onClick={onReload}>
              Atualizar diagnóstico
            </button>
          </div>
          <p className="result-count">
            Exibindo {visible.length.toLocaleString("pt-BR")} de{" "}
            {items.length.toLocaleString("pt-BR")} endpoints habilitados
          </p>
          {visible.length === 0 ? (
            <div className="empty-state">Nenhuma fonte corresponde à busca.</div>
          ) : null}
          <div className="source-health-list">
            {visible.map((item) => (
              <CollectionHealthCard item={item} key={item.endpoint_id} />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

function CollectionHealthCard({
  item,
}: Readonly<{ item: CollectionHealthItem }>) {
  const tone = healthTone(item);
  const backfill = formatBackfillProgress(item);
  return (
    <article className="source-health-card">
      <div className="card-top">
        <div>
          <h3>{item.source_name}</h3>
          <p className="meta">
            {item.endpoint_slug} · {item.endpoint_kind.toUpperCase()}
          </p>
        </div>
        <span className={`badge source-health-${tone}`}>
          {healthLabel(item.latest_partition_status)}
        </span>
      </div>
      <dl className="source-health-details">
        <div>
          <dt>Período mais recente</dt>
          <dd>{formatPeriod(item)}</dd>
        </div>
        <div>
          <dt>Registros observados</dt>
          <dd>
            {item.latest_observed_records?.toLocaleString("pt-BR") ?? "—"}
            {item.latest_expected_records !== null
              ? ` de ${item.latest_expected_records.toLocaleString("pt-BR")} esperados`
              : ""}
          </dd>
        </div>
        <div>
          <dt>Última tentativa</dt>
          <dd>
            {item.latest_attempted_at
              ? new Date(item.latest_attempted_at).toLocaleString("pt-BR")
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Defasagem da fonte</dt>
          <dd>{formatLag(item)}</dd>
        </div>
        <div>
          <dt>Execução</dt>
          <dd>
            {item.latest_run_status ?? "—"}
            {item.latest_collector_version
              ? ` · ${item.latest_collector_version}`
              : ""}
          </dd>
        </div>
      </dl>
      <p className="source-health-coverage">
        Histórico: {item.complete_partitions.toLocaleString("pt-BR")} completas
        · {item.empty_partitions.toLocaleString("pt-BR")} vazias ·{" "}
        {item.partial_partitions.toLocaleString("pt-BR")} parciais ·{" "}
        {item.failed_partitions.toLocaleString("pt-BR")} falhas ·{" "}
        {item.blocked_partitions.toLocaleString("pt-BR")} bloqueadas
      </p>
      {backfill ? (
        <section
          className="source-health-backfill"
          aria-label="Progresso retroativo do Querido Diário"
        >
          <div className="source-health-backfill-heading">
            <h4>Retroatividade desde {backfill.horizon}</h4>
            <strong>{backfill.progress}</strong>
          </div>
          <progress
            aria-label="Percentual de dias contínuos classificados"
            max={100}
            value={item.backfill_progress_percent ?? 0}
          />
          <dl>
            <div>
              <dt>Faixa contínua comprovada</dt>
              <dd>{backfill.coverage}</dd>
            </div>
            <div>
              <dt>Próxima janela pendente</dt>
              <dd>{backfill.nextWindow}</dd>
            </div>
          </dl>
          <p>
            O progresso considera somente janelas concluídas como completas ou
            vazias. “Vazia” significa que o agregador não retornou edições no
            período; não significa ausência de publicação na fonte oficial.
          </p>
        </section>
      ) : null}
      {item.latest_failure_detail ? (
        <details className="source-health-failure">
          <summary>Falha mais recente</summary>
          <p>
            <strong>{item.latest_failure_type ?? "Falha de coleta"}:</strong>{" "}
            {item.latest_failure_detail}
          </p>
          <p className="meta">
            {item.latest_failure_attempt_count?.toLocaleString("pt-BR") ?? "—"}{" "}
            tentativa(s) ·{" "}
            {item.latest_failure_retryable
              ? "nova tentativa permitida"
              : "nova tentativa não indicada"}
            {item.latest_failure_next_retry_at
              ? ` · próxima em ${new Date(item.latest_failure_next_retry_at).toLocaleString("pt-BR")}`
              : ""}
          </p>
        </details>
      ) : null}
    </article>
  );
}
