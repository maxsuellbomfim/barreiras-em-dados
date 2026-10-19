begin;

-- Correção da v10 no mesmo dia: execuções auxiliares (uma por contrato do
-- PNCP, uma por documento do TCM-BA) também ficam em collection_runs e
-- deixavam o cadastro do PNCP "em dia" com a partição falhando. A v10 passa
-- a considerar só execuções do plano de controle (metrics.control_plane).
-- As sanções da CGU fecham um ciclo completo a cada 7 dias (100 CNPJs por
-- dia; 30/09, 07/10, 14/10/2026): o prazo passa a ser o do ciclo. Falha
-- diária da fonte continua visível nas falhas abertas e na última execução.
create or replace function api.get_collection_health_v10(
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
  with health as (
    select * from api.get_collection_health_v9(page_size, observed_on)
  ),
  succeeded_runs as (
    select run.source_endpoint_id, max(run.completed_at) as completed_at
    from source.collection_runs as run
    where run.status = 'succeeded'
      and run.completed_at is not null
      -- Só execuções do plano de controle: consultas auxiliares (uma por
      -- contrato do PNCP, um documento do TCM-BA) não atestam a coleta.
      and run.metrics ->> 'control_plane' = 'true'
      and run.source_endpoint_id in (select health.endpoint_id from health)
    group by run.source_endpoint_id
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
    valid.completed_at,
    health.freshness_policy_kind,
    health.freshness_expected_hours,
    health.freshness_grace_hours,
    health.freshness_policy_note,
    case
      when health.freshness_policy_kind = 'scheduled' and valid.completed_at is not null
      then valid.completed_at + make_interval(hours => health.freshness_expected_hours + health.freshness_grace_hours)
    end,
    case
      when health.freshness_policy_kind <> 'scheduled' then 'not_monitored'
      when valid.completed_at is null then 'never_updated'
      when statement_timestamp() > valid.completed_at
        + make_interval(hours => health.freshness_expected_hours + health.freshness_grace_hours)
        then 'overdue'
      else 'current'
    end,
    case
      when health.freshness_policy_kind = 'scheduled' and valid.completed_at is not null
        and statement_timestamp() > valid.completed_at
          + make_interval(hours => health.freshness_expected_hours + health.freshness_grace_hours)
      then floor(extract(epoch from (
        statement_timestamp() - valid.completed_at
        - make_interval(hours => health.freshness_expected_hours + health.freshness_grace_hours)
      )) / 3600)::integer
      else 0
    end,
    'collection-health/1.11.0'::text,
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
    health.superseded_partitions
  from health
  left join succeeded_runs as run on run.source_endpoint_id = health.endpoint_id
  cross join lateral (
    select nullif(greatest(
      coalesce(health.latest_successful_completed_at, '-infinity'::timestamptz),
      coalesce(run.completed_at, '-infinity'::timestamptz)
    ), '-infinity'::timestamptz) as completed_at
  ) as valid;
$function$;

revoke all on function api.get_collection_health_v10(integer, date)
  from public, anon;
grant execute on function api.get_collection_health_v10(integer, date)
  to authenticated;

comment on function api.get_collection_health_v10(integer, date) is
  'Painel de coleta: além da última partição completa ou vazia, a última execução do plano de controle concluída com sucesso também é atualização válida para o frescor (collection-health/1.11.0).';


update source.source_endpoints as endpoint
set freshness_expected_hours = 168,
    freshness_grace_hours = 72,
    freshness_policy_note =
      'Lotes diários de 100 CNPJs; ciclo completo a cada ~7 dias; alerta após 10 dias sem ciclo concluído. Falha diária da fonte aparece nas falhas abertas (ADR 0089).',
    freshness_policy_version = 'source-freshness/1.2.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'sanctions-api';

notify pgrst, 'reload schema';

commit;
