begin;

-- public-availability-probe-pg/1.1.0: a sonda do banco disparava as 8 rotas
-- ao mesmo tempo; a sonda Python (GitHub) as visita uma de cada vez. Oito
-- páginas sem cache regeneradas juntas saturavam o banco e derrubavam o
-- /api/health por tempo esgotado (503 em toda hora cheia de 06 e 07/10), ou
-- seja, a sonda media a própria carga. Agora uma rota por vez: o job das
-- respostas roda a cada minuto e só dispara a próxima rota quando a anterior
-- respondeu. Prazo total de 12 minutos; rota sem resposta continua sendo
-- falha de transporte, nunca sucesso.

alter table source.public_availability_probe_requests
  alter column request_id drop not null,
  add column target_order smallint,
  add column target_path text,
  add column requested_at timestamptz;

update source.public_availability_probe_requests as request
set
  target_order = targets.target_order,
  target_path = targets.target_path,
  requested_at = run.started_at
from (values
  ('home', 1, '/'),
  ('status', 2, '/estado'),
  ('official-diary', 3, '/diario'),
  ('finance', 4, '/financas'),
  ('procurement', 5, '/licitacoes'),
  ('resources', 6, '/recursos'),
  ('representatives', 7, '/representantes'),
  ('health-api', 8, '/api/health')
) as targets(target_slug, target_order, target_path),
source.collection_runs as run
where targets.target_slug = request.target_slug
  and run.id = request.collection_run_id;

alter table source.public_availability_probe_requests
  alter column target_order set not null,
  alter column target_path set not null,
  add constraint public_availability_probe_requests_order_check
    check (target_order between 1 and 8),
  add constraint public_availability_probe_requests_path_check
    check (target_path ~ '^/[a-z/-]*$'),
  add constraint public_availability_probe_requests_fired_check
    check ((request_id is null) = (requested_at is null));

-- Dispara a próxima rota ainda não pedida de uma execução.
create function source.fire_next_public_availability_request(p_run_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $function$
declare
  next_request record;
begin
  select request.target_slug, request.target_path
  into next_request
  from source.public_availability_probe_requests as request
  where request.collection_run_id = p_run_id
    and request.request_id is null
  order by request.target_order
  limit 1;
  if not found then
    return false;
  end if;
  update source.public_availability_probe_requests
  set
    request_id = net.http_get(
      url := 'https://barreiras-em-dados.vercel.app' || next_request.target_path,
      headers := jsonb_build_object(
        'Accept', 'application/json,text/html;q=0.9',
        'User-Agent', 'Barreiras360-PublicAvailability/1.1 (pg_net)'
      ),
      timeout_milliseconds := 30000
    ),
    requested_at = statement_timestamp()
  where collection_run_id = p_run_id
    and target_slug = next_request.target_slug;
  return true;
end;
$function$;

create or replace function source.start_public_availability_probe()
returns uuid
language plpgsql
security definer
set search_path = ''
as $function$
declare
  run_id uuid;
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
      'target_count', 8,
      'request_mode', 'sequential'
    )
  from source.source_endpoints as endpoint
  join source.data_sources as data_source on data_source.id = endpoint.data_source_id
  where data_source.slug = 'barreiras-360'
    and endpoint.slug = 'critical-public-pages'
    and endpoint.enabled
  on conflict (idempotency_key) do nothing
  returning id into run_id;
  if run_id is null then
    return null;
  end if;

  insert into source.public_availability_probe_requests (
    collection_run_id, target_slug, content_kind, target_order, target_path
  )
  select run_id, targets.slug, targets.kind, targets.target_order, targets.path
  from (values
    ('home', 1, '/', 'html'),
    ('status', 2, '/estado', 'html'),
    ('official-diary', 3, '/diario', 'html'),
    ('finance', 4, '/financas', 'html'),
    ('procurement', 5, '/licitacoes', 'html'),
    ('resources', 6, '/recursos', 'html'),
    ('representatives', 7, '/representantes', 'html'),
    ('health-api', 8, '/api/health', 'health_json')
  ) as targets(slug, target_order, path, kind);

  perform source.fire_next_public_availability_request(run_id);
  return run_id;
end;
$function$;

create or replace function source.collect_public_availability_probes()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  run record;
  responses jsonb;
  pending_fired integer;
  unfired integer;
  closed integer := 0;
begin
  for run in
    select collection_run.id, collection_run.started_at
    from source.collection_runs as collection_run
    where collection_run.collector_version = 'public-availability-probe-pg/1.0.0'
      and collection_run.status = 'running'
    order by collection_run.started_at
  loop
    select
      count(*) filter (where request.request_id is not null and response.id is null),
      count(*) filter (where request.request_id is null)
    into pending_fired, unfired
    from source.public_availability_probe_requests as request
    left join net._http_response as response on response.id = request.request_id
    where request.collection_run_id = run.id;

    if (pending_fired = 0 and unfired = 0)
      or run.started_at < statement_timestamp() - interval '12 minutes'
    then
      select jsonb_agg(jsonb_build_object(
        'target_slug', request.target_slug,
        'content_kind', request.content_kind,
        'status_code', response.status_code,
        'content_type', coalesce(response.content_type, response.headers ->> 'Content-Type',
          response.headers ->> 'content-type'),
        'body', response.content,
        'latency_ms', greatest(0, (extract(epoch from (response.created - request.requested_at)) * 1000)::integer),
        'transport_failure', response.id is null or coalesce(response.timed_out, false)
          or response.error_msg is not null or response.status_code is null
      ) order by request.target_order)
      into responses
      from source.public_availability_probe_requests as request
      left join net._http_response as response on response.id = request.request_id
      where request.collection_run_id = run.id;
      perform source.record_public_availability_probe(run.id, coalesce(responses, '[]'::jsonb));
      closed := closed + 1;
    elsif pending_fired = 0 then
      -- A rota anterior já respondeu: uma nova por minuto, nunca em paralelo.
      perform source.fire_next_public_availability_request(run.id);
    end if;
  end loop;
  return closed;
end;
$function$;

revoke all on function source.fire_next_public_availability_request(uuid)
  from public, anon, authenticated, service_role;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-public-availability-collect', '* * * * *',
      'select source.collect_public_availability_probes()');
  end if;
end;
$schedule$;

commit;
