begin;

create index collection_runs_tcm_scheduler_recent_idx
  on source.collection_runs (source_endpoint_id, started_at desc)
  where collector_version = 'tcm-ba-monthly-document-collector/1.0.0'
    and metrics ->> 'execution_origin' = 'windows_scheduler';

create function api.get_collection_health_v7(
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
  latest_block_reason text,
  scheduled_success_streak integer,
  scheduled_runs_observed integer,
  latest_scheduled_run_at timestamptz
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
    'collection-health/1.7.0'::text,
    health.latest_work_completed,
    health.latest_work_total,
    health.latest_work_remaining,
    health.latest_batch_processed,
    health.latest_work_unit,
    health.latest_block_reason,
    case
      when health.source_slug = 'tcm-ba'
       and health.endpoint_slug = 'prestacoes-contas-mensais'
      then coalesce(scheduled.success_streak, 0)
    end,
    case
      when health.source_slug = 'tcm-ba'
       and health.endpoint_slug = 'prestacoes-contas-mensais'
      then coalesce(scheduled.runs_observed, 0)
    end,
    scheduled.latest_run_at
  from api.get_collection_health_v6(page_size) as health
  left join lateral (
    with recent as (
      select
        row_number() over (
          order by run.started_at desc nulls last, run.id desc
        )::integer as sequence_number,
        run.started_at,
        run.status,
        run.metrics ->> 'collection_outcome' as outcome,
        case
          when run.metrics ->> 'documents_downloaded' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'documents_downloaded')::integer
        end as downloaded,
        case
          when run.metrics ->> 'documents_preserved_before' ~ '^[0-9]{1,9}$'
          then (run.metrics ->> 'documents_preserved_before')::integer
        end as preserved_before,
        case
          when run.metrics ->> 'documents_preserved_after' ~ '^[0-9]{1,9}$'
          then (run.metrics ->> 'documents_preserved_after')::integer
        end as preserved_after,
        case
          when run.metrics ->> 'documents_remaining' ~ '^[0-9]{1,9}$'
          then (run.metrics ->> 'documents_remaining')::integer
        end as remaining,
        case
          when run.cursor_after ->> 'expected_documents' ~ '^[0-9]{1,9}$'
          then (run.cursor_after ->> 'expected_documents')::integer
        end as expected
      from source.collection_runs as run
      where run.source_endpoint_id = health.endpoint_id
        and run.collector_version =
          'tcm-ba-monthly-document-collector/1.0.0'
        and run.metrics ->> 'execution_origin' = 'windows_scheduler'
      order by run.started_at desc nulls last, run.id desc
      limit 7
    ), validated as (
      select
        recent.*,
        coalesce(
          downloaded between 1 and 10
            and preserved_before >= 0
            and preserved_after = preserved_before + downloaded
            and remaining >= 0
            and expected > 0
            and preserved_after + remaining = expected
            and (
              (status = 'partial' and outcome = 'partial' and remaining > 0)
              or
              (status = 'succeeded' and outcome = 'complete' and remaining = 0)
            ),
          false
        ) as is_valid
      from recent
    ), summarized as (
      select
        count(*)::integer as runs_observed,
        min(sequence_number) filter (where not is_valid) as first_invalid,
        max(started_at) filter (where sequence_number = 1) as latest_run_at
      from validated
    )
    select
      greatest(
        0,
        coalesce(first_invalid - 1, runs_observed)
      )::integer as success_streak,
      runs_observed,
      latest_run_at
    from summarized
  ) as scheduled
    on health.source_slug = 'tcm-ba'
   and health.endpoint_slug = 'prestacoes-contas-mensais';
$function$;

revoke all on function api.get_collection_health_v7(integer)
  from public, anon;
grant execute on function api.get_collection_health_v7(integer)
  to authenticated;

comment on function api.get_collection_health_v7(integer) is
  'Diagnóstico interno que mede prospectivamente até sete lotes íntegros identificados como Windows Scheduler; não infere origem histórica nem expõe métricas brutas.';

notify pgrst, 'reload schema';

commit;
