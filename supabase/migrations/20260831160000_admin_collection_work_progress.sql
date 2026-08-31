begin;

create function api.get_collection_health_v4(
  page_size integer default 200
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
  latest_batch_processed integer
)
language sql
stable
security definer
set search_path = ''
as $function$
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
    health.partial_partitions,
    health.failed_partitions,
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
    'collection-health/1.4.0'::text,
    case when progress.is_valid then progress.total - progress.remaining end,
    case when progress.is_valid then progress.total end,
    case when progress.is_valid then progress.remaining end,
    case when progress.is_valid then progress.batch end
  from api.get_collection_health_v3(page_size) as health
  left join source.collection_partitions as partition
    on partition.source_endpoint_id = health.endpoint_id
   and partition.partition_key = health.latest_partition_key
  left join lateral (
    select
      parsed.total,
      parsed.remaining,
      parsed.batch,
      parsed.total > 0
        and parsed.remaining <= parsed.total
        and parsed.batch <= parsed.total - parsed.remaining as is_valid
    from (
      select
        case
          when partition.checkpoint ->> 'total_suppliers' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'total_suppliers')::integer
        end as total,
        case
          when partition.checkpoint ->> 'remaining_suppliers' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'remaining_suppliers')::integer
        end as remaining,
        case
          when partition.checkpoint ->> 'queried_cnpjs' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'queried_cnpjs')::integer
        end as batch
    ) as parsed
  ) as progress on true;
$function$;

revoke all on function api.get_collection_health_v4(integer)
  from public, anon;
grant execute on function api.get_collection_health_v4(integer)
  to authenticated;

comment on function api.get_collection_health_v4(integer) is
  'Diagnóstico interno com progresso numérico sanitizado de ciclos retomáveis; não expõe cursores, identificadores nem checkpoints brutos.';

notify pgrst, 'reload schema';

commit;
