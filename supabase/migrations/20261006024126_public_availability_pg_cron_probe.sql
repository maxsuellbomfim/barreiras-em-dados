begin;

-- public-availability-probe-pg/1.0.0: o GitHub Actions executa o cron horário
-- da sonda só ~4–5 vezes por dia e o gate de prontidão exige 20 sondagens
-- agendadas por dia encerrado. O próprio banco passa a sondar as mesmas 8
-- rotas críticas a cada hora (pg_cron + pg_net), com o mesmo contrato
-- (public-availability-contract/1.0.0) e o mesmo formato de execução.
-- pg_net é assíncrono: um job dispara as requisições e outro, minutos depois,
-- lê as respostas e fecha a execução. Resposta ausente após 5 minutos conta
-- como falha de transporte, nunca como sucesso.

do $extensions$
begin
  -- PGlite (testes) não tem as extensões: só a parte de rede fica de fora.
  if exists (select 1 from pg_available_extensions where name = 'pg_net') then
    execute 'create extension if not exists pg_net';
  end if;
  if exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    execute 'create extension if not exists pg_cron with schema pg_catalog';
  end if;
end;
$extensions$;

create table source.public_availability_probe_requests (
  collection_run_id uuid not null references source.collection_runs(id),
  target_slug text not null check (target_slug ~ '^[a-z-]{2,32}$'),
  content_kind text not null check (content_kind in ('html', 'health_json')),
  request_id bigint not null,
  primary key (collection_run_id, target_slug)
);

alter table source.public_availability_probe_requests enable row level security;
revoke all on source.public_availability_probe_requests from public, anon, authenticated;

-- Mesmo contrato do coletor Python (_valid_health_contract): devolve o status
-- declarado quando o JSON de /api/health é válido, senão null.
create function source.public_availability_health_status_v1(
  p_status_code integer,
  p_content_type text,
  p_body text
)
returns text
language plpgsql
immutable
set search_path = ''
as $function$
declare
  payload jsonb;
  checks jsonb;
  item jsonb;
  declared text;
  expected text;
  available integer := 0;
  unavailable integer := 0;
  keys text[] := '{}';
begin
  if coalesce(lower(p_content_type), '') not like 'application/json%' then
    return null;
  end if;
  begin
    payload := p_body::jsonb;
  exception when others then
    return null;
  end;
  if jsonb_typeof(payload) <> 'object' then
    return null;
  end if;
  declared := payload ->> 'status';
  checks := payload -> 'checks';
  if payload ->> 'service' is distinct from 'barreiras-em-dados-web'
    or jsonb_typeof(payload -> 'status') is distinct from 'string'
    or declared not in ('ok', 'degraded')
    or jsonb_typeof(payload -> 'httpStatus') is distinct from 'number'
    or (payload ->> 'httpStatus') is distinct from p_status_code::text
    or jsonb_typeof(checks) is distinct from 'array'
    or jsonb_array_length(checks) <> 3
  then
    return null;
  end if;
  for item in select value from jsonb_array_elements(checks) loop
    if jsonb_typeof(item) <> 'object'
      or jsonb_typeof(item -> 'key') is distinct from 'string'
      or jsonb_typeof(item -> 'status') is distinct from 'string'
      or item ->> 'key' not in ('diary', 'finance', 'representatives')
      or item ->> 'status' not in ('available', 'empty', 'unavailable')
    then
      return null;
    end if;
    if item ->> 'status' = 'unavailable' then
      if item ? 'records' and jsonb_typeof(item -> 'records') <> 'null' then
        return null;
      end if;
      unavailable := unavailable + 1;
    else
      if jsonb_typeof(item -> 'records') is distinct from 'number'
        or (item ->> 'records') !~ '^[0-9]+$'
        or (((item ->> 'records')::bigint > 0) <> (item ->> 'status' = 'available'))
      then
        return null;
      end if;
      if item ->> 'status' = 'available' then
        available := available + 1;
      end if;
    end if;
    keys := keys || (item ->> 'key');
  end loop;
  if (select count(distinct key) from unnest(keys) as key) <> 3 then
    return null;
  end if;
  expected := case
    when available = 3 then 'ok'
    when unavailable = 3 then 'unavailable'
    else 'degraded'
  end;
  return case when declared = expected then declared end;
end;
$function$;

-- Fecha uma execução a partir das respostas coletadas. Cada item:
-- {target_slug, content_kind, status_code, content_type, body, latency_ms,
--  transport_failure}. Sem rede: testável sem pg_net.
create function source.record_public_availability_probe(
  p_run_id uuid,
  p_responses jsonb
)
returns text
language plpgsql
security definer
set search_path = ''
as $function$
declare
  item jsonb;
  checked integer := 0;
  valid integer := 0;
  http_5xx integer := 0;
  non_2xx integer := 0;
  transport integer := 0;
  contract integer := 0;
  latency integer := 0;
  code integer;
  health text;
  health_status text;
  passed boolean;
begin
  if jsonb_typeof(p_responses) is distinct from 'array' then
    raise exception 'respostas devem ser uma lista' using errcode = '22023';
  end if;
  for item in select value from jsonb_array_elements(p_responses) loop
    checked := checked + 1;
    if coalesce((item ->> 'transport_failure')::boolean, false)
      or jsonb_typeof(item -> 'status_code') is distinct from 'number'
    then
      transport := transport + 1;
      continue;
    end if;
    code := (item ->> 'status_code')::integer;
    latency := greatest(latency, coalesce((item ->> 'latency_ms')::integer, 0));
    if code not between 200 and 299 then
      non_2xx := non_2xx + 1;
      if code between 500 and 599 then
        http_5xx := http_5xx + 1;
      end if;
      continue;
    end if;
    if item ->> 'content_kind' = 'health_json' then
      health := source.public_availability_health_status_v1(
        code, item ->> 'content_type', item ->> 'body');
      if health is null then
        contract := contract + 1;
        continue;
      end if;
      health_status := health;
    elsif coalesce(lower(item ->> 'content_type'), '') not like 'text/html%'
      or lower(coalesce(item ->> 'body', '')) not like '%<html%'
      or lower(coalesce(item ->> 'body', '')) not like '%barreiras 360%'
    then
      contract := contract + 1;
      continue;
    end if;
    valid := valid + 1;
  end loop;

  passed := checked = 8 and valid = 8 and non_2xx = 0 and transport = 0 and contract = 0;
  update source.collection_runs as run
  set
    status = case when passed then 'succeeded' else 'partial' end,
    completed_at = statement_timestamp(),
    heartbeat_at = statement_timestamp(),
    cursor_after = jsonb_build_object('target_slugs', jsonb_build_array(
      'home', 'status', 'official-diary', 'finance', 'procurement', 'resources',
      'representatives', 'health-api')),
    error_code = case when passed then null else 'PublicAvailabilityGateFailure' end,
    error_detail = case when passed then null else
      'Uma ou mais rotas públicas críticas não responderam com HTTP 2xx e contrato válido.'
    end,
    metrics = run.metrics || jsonb_build_object(
      'targets_checked', checked,
      'http_5xx_count', http_5xx,
      'http_non_2xx_count', non_2xx,
      'transport_failures', transport,
      'contract_failures', contract,
      'health_status', health_status,
      'maximum_latency_ms', latency,
      'collection_outcome', case when passed then 'complete' else 'partial' end
    )
  where run.id = p_run_id
    and run.status = 'running'
    and run.collector_version = 'public-availability-probe-pg/1.0.0';
  if not found then
    raise exception 'execução de sondagem inexistente ou já encerrada' using errcode = '22023';
  end if;
  return case when passed then 'complete' else 'partial' end;
end;
$function$;

create function source.start_public_availability_probe()
returns uuid
language plpgsql
security definer
set search_path = ''
as $function$
declare
  run_id uuid;
  target record;
  observed_on date := (statement_timestamp() at time zone 'America/Bahia')::date;
begin
  insert into source.collection_runs (
    source_endpoint_id, idempotency_key, collector_version, parser_version,
    collection_window_start, collection_window_end, status, attempt_count,
    started_at, heartbeat_at, metrics
  )
  select
    endpoint.id,
    'public-availability:pg-cron:'
      || to_char(statement_timestamp() at time zone 'UTC', 'YYYY-MM-DD"T"HH24'),
    'public-availability-probe-pg/1.0.0',
    'public-availability-contract/1.0.0',
    observed_on::timestamp at time zone 'UTC',
    observed_on::timestamp at time zone 'UTC',
    'running',
    1,
    statement_timestamp(),
    statement_timestamp(),
    jsonb_build_object(
      'control_plane', true,
      'execution_origin', 'supabase_pg_cron',
      'workflow_event', 'schedule',
      'target_count', 8
    )
  from source.source_endpoints as endpoint
  join source.data_sources as data_source on data_source.id = endpoint.data_source_id
  where data_source.slug = 'barreiras-360'
    and endpoint.slug = 'critical-public-pages'
    and endpoint.enabled
  -- Uma por hora: novo disparo na mesma hora não duplica a sondagem.
  on conflict (idempotency_key) do nothing
  returning id into run_id;
  if run_id is null then
    return null;
  end if;

  for target in
    select * from (values
      ('home', '/', 'html'),
      ('status', '/estado', 'html'),
      ('official-diary', '/diario', 'html'),
      ('finance', '/financas', 'html'),
      ('procurement', '/licitacoes', 'html'),
      ('resources', '/recursos', 'html'),
      ('representatives', '/representantes', 'html'),
      ('health-api', '/api/health', 'health_json')
    ) as targets(slug, path, kind)
  loop
    insert into source.public_availability_probe_requests (
      collection_run_id, target_slug, content_kind, request_id
    ) values (
      run_id,
      target.slug,
      target.kind,
      net.http_get(
        url := 'https://barreiras-em-dados.vercel.app' || target.path,
        headers := jsonb_build_object(
          'Accept', 'application/json,text/html;q=0.9',
          'User-Agent', 'Barreiras360-PublicAvailability/1.0 (pg_net)'
        ),
        timeout_milliseconds := 30000
      )
    );
  end loop;
  return run_id;
end;
$function$;

-- Lê as respostas do pg_net e fecha as execuções em aberto. Resposta que não
-- chegou em 5 minutos vira falha de transporte (a sondagem fica partial).
create function source.collect_public_availability_probes()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  run record;
  responses jsonb;
  closed integer := 0;
begin
  for run in
    select collection_run.id, collection_run.started_at
    from source.collection_runs as collection_run
    where collection_run.collector_version = 'public-availability-probe-pg/1.0.0'
      and collection_run.status = 'running'
    order by collection_run.started_at
  loop
    select jsonb_agg(jsonb_build_object(
      'target_slug', request.target_slug,
      'content_kind', request.content_kind,
      'status_code', response.status_code,
      'content_type', coalesce(response.content_type, response.headers ->> 'Content-Type',
        response.headers ->> 'content-type'),
      'body', response.content,
      'latency_ms', greatest(0, (extract(epoch from (response.created - run.started_at)) * 1000)::integer),
      'transport_failure', response.id is null or coalesce(response.timed_out, false)
        or response.error_msg is not null or response.status_code is null
    ) order by request.target_slug)
    into responses
    from source.public_availability_probe_requests as request
    left join net._http_response as response on response.id = request.request_id
    where request.collection_run_id = run.id;

    if responses is null then
      responses := '[]'::jsonb;
    end if;
    if jsonb_array_length(responses) = 8
      and not exists (
        select 1 from jsonb_array_elements(responses) as item
        where (item.value ->> 'transport_failure')::boolean
      )
      or run.started_at < statement_timestamp() - interval '5 minutes'
    then
      perform source.record_public_availability_probe(run.id, responses);
      closed := closed + 1;
    end if;
  end loop;
  return closed;
end;
$function$;

revoke all on function source.public_availability_health_status_v1(integer, text, text)
  from public, anon, authenticated;
revoke all on function source.record_public_availability_probe(uuid, jsonb)
  from public, anon, authenticated, service_role;
revoke all on function source.start_public_availability_probe()
  from public, anon, authenticated, service_role;
revoke all on function source.collect_public_availability_probes()
  from public, anon, authenticated, service_role;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-public-availability-probe', '17 * * * *',
      'select source.start_public_availability_probe()');
    perform cron.schedule('barreiras-public-availability-collect', '*/5 * * * *',
      'select source.collect_public_availability_probes()');
  end if;
end;
$schedule$;

-- O gate de disponibilidade passa a contar também a sonda do banco.
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
    'collection-health/1.9.0'::text,
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
        and (
          (run.collector_version = 'public-availability-probe/1.0.0'
            and run.metrics ->> 'execution_origin' = 'github_actions')
          -- 1.9.0: sonda horária do próprio banco (pg_cron), mesmo contrato.
          or (run.collector_version = 'public-availability-probe-pg/1.0.0'
            and run.metrics ->> 'execution_origin' = 'supabase_pg_cron')
        )
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
            and (
              (run.collector_version = 'public-availability-probe/1.0.0'
                and run.metrics ->> 'execution_origin' = 'github_actions')
              -- 1.9.0: sonda horária do próprio banco (pg_cron), mesmo contrato.
              or (run.collector_version = 'public-availability-probe-pg/1.0.0'
                and run.metrics ->> 'execution_origin' = 'supabase_pg_cron')
            )
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
