begin;

-- Count only closed days that actually exist since instrumentation began.
create or replace function api.get_collection_health_v8(
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
  availability_daily_history jsonb
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
    'collection-health/1.8.0'::text,
    health.latest_work_completed,
    health.latest_work_total,
    health.latest_work_remaining,
    health.latest_batch_processed,
    health.latest_work_unit,
    health.latest_block_reason,
    health.scheduled_success_streak,
    health.scheduled_runs_observed,
    health.latest_scheduled_run_at,
    case
      when health.source_slug = 'barreiras-360'
       and health.endpoint_slug = 'critical-public-pages'
      then coalesce(availability.success_streak_days, 0)
    end,
    case
      when health.source_slug = 'barreiras-360'
       and health.endpoint_slug = 'critical-public-pages'
      then coalesce(availability.days_observed, 0)
    end,
    availability.latest_probe_at,
    case
      when health.source_slug = 'barreiras-360'
       and health.endpoint_slug = 'critical-public-pages'
      then 20
    end,
    availability.daily_history
  from api.get_collection_health_v7(page_size) as health
  left join lateral (
    with closed_days as (
      select generated.day::date as day
      from generate_series(
        (observed_on - 7)::timestamp,
        (observed_on - 1)::timestamp,
        interval '1 day'
      ) as generated(day)
      where generated.day::date >= (
        select (endpoint.created_at at time zone 'America/Bahia')::date
        from source.source_endpoints as endpoint
        where endpoint.id = health.endpoint_id
      )
    ), parsed_runs as (
      select
        (run.started_at at time zone 'America/Bahia')::date as day,
        run.id,
        run.started_at,
        run.status,
        run.metrics ->> 'collection_outcome' as outcome,
        case when run.metrics ->> 'target_count' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'target_count')::integer end as target_count,
        case when run.metrics ->> 'targets_checked' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'targets_checked')::integer end as targets_checked,
        case when run.metrics ->> 'http_5xx_count' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'http_5xx_count')::integer end as http_5xx_count,
        case when run.metrics ->> 'http_non_2xx_count' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'http_non_2xx_count')::integer end as http_non_2xx_count,
        case when run.metrics ->> 'transport_failures' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'transport_failures')::integer end as transport_failures,
        case when run.metrics ->> 'contract_failures' ~ '^[0-9]{1,2}$'
          then (run.metrics ->> 'contract_failures')::integer end as contract_failures,
        run.metrics ->> 'health_status' as health_status
      from source.collection_runs as run
      where run.source_endpoint_id = health.endpoint_id
        and run.collector_version = 'public-availability-probe/1.0.0'
        and run.metrics ->> 'execution_origin' = 'github_actions'
        and (
          run.metrics ->> 'workflow_event' = 'schedule'
          or (
            run.status in ('running', 'failed')
            and not (run.metrics ? 'workflow_event')
          )
        )
        and run.started_at >= ((observed_on - 7)::timestamp at time zone 'America/Bahia')
        and run.started_at < (observed_on::timestamp at time zone 'America/Bahia')
    ), daily as (
      select
        closed_days.day,
        count(parsed_runs.id)::integer as runs_observed,
        count(parsed_runs.id) filter (
          where parsed_runs.status = 'succeeded'
            and parsed_runs.outcome = 'complete'
            and parsed_runs.target_count = 8
            and parsed_runs.targets_checked = 8
            and parsed_runs.http_5xx_count = 0
            and parsed_runs.http_non_2xx_count = 0
            and parsed_runs.transport_failures = 0
            and parsed_runs.contract_failures = 0
            and parsed_runs.health_status in ('ok', 'degraded')
        )::integer as valid_runs,
        coalesce(sum(parsed_runs.http_5xx_count), 0)::integer as http_5xx_count
      from closed_days
      left join parsed_runs on parsed_runs.day = closed_days.day
      group by closed_days.day
    ), classified as (
      select
        daily.*,
        row_number() over (order by daily.day desc)::integer as sequence_number,
        case
          when daily.runs_observed = 0 then 'missing'
          when daily.valid_runs <> daily.runs_observed then 'failed'
          when daily.runs_observed >= 20 then 'passed'
          else 'incomplete'
        end as state
      from daily
    ), summarized as (
      select
        case
          when count(*) = 0 then 0
          else greatest(
            0,
            coalesce(
              min(sequence_number) filter (where state <> 'passed') - 1,
              count(*)::integer
            )
          )::integer
        end as success_streak_days,
        count(*) filter (where runs_observed > 0)::integer as days_observed,
        (
          select max(run.started_at)
          from source.collection_runs as run
          where run.source_endpoint_id = health.endpoint_id
            and run.collector_version = 'public-availability-probe/1.0.0'
            and run.metrics ->> 'execution_origin' = 'github_actions'
        ) as latest_probe_at,
        coalesce(
          jsonb_agg(
            jsonb_build_object(
              'day', day,
              'state', state,
              'runs_observed', runs_observed,
              'valid_runs', valid_runs,
              'http_5xx_count', http_5xx_count
            )
            order by day desc
          )
          filter (where day is not null),
          '[]'::jsonb
        ) as daily_history
      from classified
    )
    select * from summarized
  ) as availability
    on health.source_slug = 'barreiras-360'
   and health.endpoint_slug = 'critical-public-pages';
$function$;

revoke all on function api.get_collection_health_v8(integer, date)
  from public, anon;
grant execute on function api.get_collection_health_v8(integer, date)
  to authenticated;

comment on function api.get_collection_health_v8(integer, date) is
  'Diagnóstico interno de sete dias encerrados com ao menos vinte sondagens sintéticas agendadas; não representa todo o tráfego da Vercel.';

notify pgrst, 'reload schema';

commit;
