begin;

create function api.get_collection_health_v6(
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
  latest_batch_processed integer,
  latest_work_unit text,
  latest_block_reason text
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
    'collection-health/1.6.0'::text,
    case
      when progress.is_valid then progress.completed
      else health.latest_work_completed
    end,
    case
      when progress.is_valid then progress.total
      else health.latest_work_total
    end,
    case
      when progress.is_valid then progress.remaining
      else health.latest_work_remaining
    end,
    case
      when progress.is_valid then progress.batch
      else health.latest_batch_processed
    end,
    case when progress.is_valid then 'document'::text end,
    health.latest_block_reason
  from api.get_collection_health_v5(page_size) as health
  left join source.collection_partitions as partition
    on partition.source_endpoint_id = health.endpoint_id
   and partition.partition_key = health.latest_partition_key
  left join source.collection_runs as run
    on run.id = partition.collection_run_id
  left join lateral (
    select
      parsed.total,
      parsed.completed,
      parsed.remaining,
      parsed.batch,
      parsed.total > 0
        and parsed.completed >= 0
        and parsed.remaining >= 0
        and parsed.completed + parsed.remaining = parsed.total
        and parsed.batch between 1 and least(10, parsed.completed)
        as is_valid
    from (
      select
        case
          when partition.checkpoint ->> 'expected_documents' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'expected_documents')::integer
        end as total,
        case
          when partition.checkpoint ->> 'preserved_documents' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'preserved_documents')::integer
        end as completed,
        case
          when partition.checkpoint ->> 'remaining_documents' ~ '^[0-9]{1,9}$'
          then (partition.checkpoint ->> 'remaining_documents')::integer
        end as remaining,
        case
          when run.metrics ->> 'documents_downloaded' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'documents_downloaded')::integer
        end as batch
    ) as parsed
    where health.source_slug = 'tcm-ba'
      and partition.partition_key ~ '^documents:[0-9]{4}-(0[1-9]|1[0-2])$'
  ) as progress on true;
$function$;

revoke all on function api.get_collection_health_v6(integer)
  from public, anon;
grant execute on function api.get_collection_health_v6(integer)
  to authenticated;

comment on function api.get_collection_health_v6(integer) is
  'Diagnóstico interno com progresso documental TCM-BA sanitizado; não expõe hashes, cursores, checkpoints ou métricas brutas.';

notify pgrst, 'reload schema';

commit;
