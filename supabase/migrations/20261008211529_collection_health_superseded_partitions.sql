begin;

-- Partições parciais ou falhas cujo período foi coberto depois por uma
-- janela maior completa ou vazia do mesmo endpoint não são pendência: o
-- PNCP refaz a janela inteira (2025-04-09..23 coberta por 2025-04-09..05-08)
-- e a verificação integral da janela sem modalidade pendente cobre as
-- subpartições por modalidade (2024-03-15..04-13, modalidades 9 e 11).
-- Mesma leitura das regras 2 e 4 da reconciliação de falhas, aplicada à
-- contagem do painel (collection-health/1.10.0). O histórico das partições
-- não muda; só a contagem separa "cobertas" de "pendentes".
create function api.get_collection_health_v9(
  page_size integer default 200,
  observed_on date default ((statement_timestamp() at time zone 'America/Bahia')::date)
)
returns table (
  endpoint_id uuid,
  source_slug text,
  source_name text,
  source_status text,
  endpoint_slug text,
  endpoint_kind text,
  endpoint_enabled boolean,
  latest_partition_key text,
  latest_partition_status text,
  latest_period_start date,
  latest_period_end date,
  latest_expected_records integer,
  latest_observed_records integer,
  latest_attempted_at timestamptz,
  latest_completed_at timestamptz,
  latest_run_status text,
  latest_collector_version text,
  complete_partitions bigint,
  empty_partitions bigint,
  partial_partitions bigint,
  failed_partitions bigint,
  blocked_partitions bigint,
  unresolved_failures bigint,
  latest_failure_status text,
  latest_failure_type text,
  latest_failure_detail text,
  latest_failure_attempt_count integer,
  latest_failure_retryable boolean,
  latest_failure_next_retry_at timestamptz,
  latest_failure_at timestamptz,
  backfill_horizon date,
  continuous_coverage_start date,
  continuous_coverage_end date,
  next_backfill_start date,
  next_backfill_end date,
  backfill_classified_days integer,
  backfill_total_days integer,
  backfill_progress_percent double precision,
  latest_successful_partition_status text,
  latest_successful_period_start date,
  latest_successful_period_end date,
  latest_successful_observed_records integer,
  latest_successful_completed_at timestamptz,
  freshness_policy_kind text,
  freshness_expected_hours integer,
  freshness_grace_hours integer,
  freshness_policy_note text,
  freshness_due_at timestamptz,
  freshness_status text,
  freshness_overdue_hours integer,
  methodology_version text,
  latest_work_completed integer,
  latest_work_total integer,
  latest_work_remaining integer,
  latest_batch_processed integer,
  latest_work_unit text,
  latest_block_reason text,
  scheduled_success_streak integer,
  scheduled_runs_observed integer,
  latest_scheduled_run_at timestamptz,
  availability_success_streak_days integer,
  availability_days_observed integer,
  availability_latest_probe_at timestamptz,
  availability_expected_runs_per_day integer,
  availability_daily_history jsonb,
  superseded_partitions bigint
)
language sql
stable
security definer
set search_path = ''
as $function$
  with superseded as (
    select
      stale.source_endpoint_id,
      count(*)::bigint as total,
      count(*) filter (where stale.status = 'partial')::bigint as partial_total,
      count(*) filter (where stale.status = 'failed')::bigint as failed_total
    from source.collection_partitions as stale
    where stale.status in ('partial', 'failed')
      and (
        -- Retratos datados (catálogo, arquivo, dia): um retrato posterior
        -- bem-sucedido do mesmo tipo substitui o que falhou (regra 2 da
        -- reconciliação de falhas).
        (
          stale.partition_key
            ~ '^(catalog-snapshot|archive-snapshot|day):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          and exists (
            select 1
            from source.collection_partitions as later
            where later.source_endpoint_id = stale.source_endpoint_id
              and split_part(later.partition_key, ':', 1)
                = split_part(stale.partition_key, ':', 1)
              and later.partition_key
                ~ '^(catalog-snapshot|archive-snapshot|day):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
              and later.status in ('complete', 'empty')
              and later.completed_at > coalesce(
                stale.completed_at, stale.last_attempted_at, stale.updated_at
              )
          )
        )
        -- Janelas publicadas (PNCP): janela maior posterior cujo nome registra
        -- o período inteiro (regra 4); a subpartição por modalidade só sai
        -- quando a janela integral não deixou essa modalidade pendente.
        or (
          stale.partition_key ~ (
            '^published:[0-9]{4}-[0-9]{2}-[0-9]{2}:[0-9]{4}-[0-9]{2}-[0-9]{2}'
            || '(:modality:[0-9]+)?$'
          )
          and exists (
            select 1
            from source.collection_partitions as covering
            where covering.source_endpoint_id = stale.source_endpoint_id
              and covering.partition_key = (
                'published:' || covering.period_start::text || ':'
                || covering.period_end::text
              )
              and covering.partition_key <> stale.partition_key
              and covering.status in ('complete', 'empty')
              and covering.period_start
                <= split_part(stale.partition_key, ':', 2)::date
              and covering.period_end
                >= split_part(stale.partition_key, ':', 3)::date
              and covering.completed_at > coalesce(
                stale.completed_at, stale.last_attempted_at, stale.updated_at
              )
              and not (
                coalesce(covering.checkpoint -> 'failed_modalities', '[]'::jsonb)
                || coalesce(covering.checkpoint -> 'deferred_modalities', '[]'::jsonb)
                || coalesce(covering.checkpoint -> 'truncated_modalities', '[]'::jsonb)
              ) @> coalesce(
                to_jsonb(substring(stale.partition_key from ':modality:([0-9]+)$')::integer),
                '"none"'::jsonb
              )
          )
        )
      )
    group by stale.source_endpoint_id
  )
  select
    health.endpoint_id,
    health.source_slug,
    health.source_name,
    health.source_status,
    health.endpoint_slug,
    health.endpoint_kind,
    health.endpoint_enabled,
    health.latest_partition_key,
    health.latest_partition_status,
    health.latest_period_start,
    health.latest_period_end,
    health.latest_expected_records,
    health.latest_observed_records,
    health.latest_attempted_at,
    health.latest_completed_at,
    health.latest_run_status,
    health.latest_collector_version,
    health.complete_partitions,
    health.empty_partitions,
    health.partial_partitions - coalesce(superseded.partial_total, 0),
    health.failed_partitions - coalesce(superseded.failed_total, 0),
    health.blocked_partitions,
    health.unresolved_failures,
    health.latest_failure_status,
    health.latest_failure_type,
    health.latest_failure_detail,
    health.latest_failure_attempt_count,
    health.latest_failure_retryable,
    health.latest_failure_next_retry_at,
    health.latest_failure_at,
    health.backfill_horizon,
    health.continuous_coverage_start,
    health.continuous_coverage_end,
    health.next_backfill_start,
    health.next_backfill_end,
    health.backfill_classified_days,
    health.backfill_total_days,
    health.backfill_progress_percent,
    health.latest_successful_partition_status,
    health.latest_successful_period_start,
    health.latest_successful_period_end,
    health.latest_successful_observed_records,
    health.latest_successful_completed_at,
    health.freshness_policy_kind,
    health.freshness_expected_hours,
    health.freshness_grace_hours,
    health.freshness_policy_note,
    health.freshness_due_at,
    health.freshness_status,
    health.freshness_overdue_hours,
    'collection-health/1.10.0'::text,
    health.latest_work_completed,
    health.latest_work_total,
    health.latest_work_remaining,
    health.latest_batch_processed,
    health.latest_work_unit,
    health.latest_block_reason,
    health.scheduled_success_streak,
    health.scheduled_runs_observed,
    health.latest_scheduled_run_at,
    health.availability_success_streak_days,
    health.availability_days_observed,
    health.availability_latest_probe_at,
    health.availability_expected_runs_per_day,
    health.availability_daily_history,
    coalesce(superseded.total, 0)::bigint
  from api.get_collection_health_v8(page_size, observed_on) as health
  left join superseded on superseded.source_endpoint_id = health.endpoint_id;
$function$;

revoke all on function api.get_collection_health_v9(integer, date)
  from public, anon;
grant execute on function api.get_collection_health_v9(integer, date)
  to authenticated;

comment on function api.get_collection_health_v9(integer, date) is
  'Painel de coleta: partições parciais ou falhas cobertas por janela posterior completa ou vazia saem de parciais/falhas e entram em superseded_partitions (collection-health/1.10.0).';

notify pgrst, 'reload schema';

commit;
