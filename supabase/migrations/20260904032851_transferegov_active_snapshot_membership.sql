begin;

-- O acervo bruto continua append-only. Estas tabelas registram apenas quais
-- versoes exatas pertencem a cada retrato anual validado da API atual.
create table source.transferegov_snapshot_manifests (
  id uuid primary key default gen_random_uuid(),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  collection_run_id uuid not null references source.collection_runs(id),
  fiscal_year smallint not null check (fiscal_year >= 2021),
  status text not null check (
    status in ('pending', 'active', 'superseded', 'abandoned')
  ),
  record_count integer not null check (record_count >= 0),
  snapshot_fingerprint text not null check (
    snapshot_fingerprint ~ '^[0-9a-f]{64}$'
  ),
  staged_at timestamptz not null default statement_timestamp(),
  activated_at timestamptz,
  superseded_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  unique (collection_run_id, fiscal_year),
  check (status not in ('active', 'superseded') or activated_at is not null),
  check (status <> 'superseded' or superseded_at is not null)
);

create unique index transferegov_snapshot_manifests_active_idx
  on source.transferegov_snapshot_manifests (
    source_endpoint_id,
    fiscal_year
  )
  where status = 'active';

create index transferegov_snapshot_manifests_run_idx
  on source.transferegov_snapshot_manifests (collection_run_id, status);

create index transferegov_snapshot_manifests_endpoint_year_idx
  on source.transferegov_snapshot_manifests (
    source_endpoint_id,
    fiscal_year,
    status
  );

create table source.transferegov_snapshot_records (
  snapshot_id uuid not null
    references source.transferegov_snapshot_manifests(id) on delete cascade,
  raw_record_id uuid not null references raw.raw_records(id),
  record_type text not null check (length(btrim(record_type)) > 0),
  source_record_key text not null check (length(btrim(source_record_key)) > 0),
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default statement_timestamp(),
  primary key (snapshot_id, record_type, source_record_key),
  unique (snapshot_id, raw_record_id)
);

create index transferegov_snapshot_records_raw_idx
  on source.transferegov_snapshot_records (raw_record_id);

alter table source.transferegov_snapshot_manifests enable row level security;
alter table source.transferegov_snapshot_records enable row level security;

revoke all on table
  source.transferegov_snapshot_manifests,
  source.transferegov_snapshot_records
from public, anon, authenticated, collector_worker;

create function source.stage_transferegov_snapshot(
  p_collection_run_id uuid,
  p_fiscal_year smallint,
  p_records jsonb,
  p_snapshot_fingerprint text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_endpoint_id uuid;
  v_run_status text;
  v_snapshot_id uuid;
  v_record_count integer;
  v_distinct_count integer;
  v_inserted_count integer;
  v_computed_fingerprint text;
  v_target_status text;
begin
  if p_fiscal_year < 2021
     or p_fiscal_year > extract(year from current_date)::smallint then
    raise exception 'Exercicio fiscal invalido para o snapshot Transferegov.';
  end if;
  if p_records is null
     or jsonb_typeof(p_records) <> 'array' then
    raise exception 'A evidencia do snapshot Transferegov deve ser uma lista.';
  end if;
  if p_snapshot_fingerprint is null
     or p_snapshot_fingerprint !~ '^[0-9a-f]{64}$' then
    raise exception 'A impressao do snapshot Transferegov e invalida.';
  end if;
  if exists (
    select 1
    from jsonb_array_elements(p_records) as supplied(item)
    where jsonb_typeof(supplied.item) <> 'object'
       or supplied.item - array[
            'record_type', 'source_record_key', 'payload_sha256'
          ] <> '{}'::jsonb
       or jsonb_typeof(supplied.item -> 'record_type') <> 'string'
       or jsonb_typeof(supplied.item -> 'source_record_key') <> 'string'
       or jsonb_typeof(supplied.item -> 'payload_sha256') <> 'string'
       or supplied.item ->> 'record_type' not in (
            'transferegov_proposta',
            'transferegov_distribuicao_recurso',
            'transferegov_parceria',
            'transferegov_empenho',
            'transferegov_documento_habil',
            'transferegov_ordem_pagamento',
            'transferegov_ordem_bancaria'
          )
       or length(btrim(supplied.item ->> 'source_record_key')) = 0
       or supplied.item ->> 'payload_sha256' !~ '^[0-9a-f]{64}$'
  ) then
    raise exception 'A evidencia do snapshot Transferegov viola o contrato minimo.';
  end if;

  with supplied as (
    select
      item ->> 'record_type' as record_type,
      item ->> 'source_record_key' as source_record_key,
      item ->> 'payload_sha256' as payload_sha256
    from jsonb_array_elements(p_records) as input(item)
  ), canonical as (
    select
      record_type || chr(31) || source_record_key || chr(31) ||
      payload_sha256 as line
    from supplied
  )
  select
    (select count(*)::integer from supplied),
    (
      select count(distinct (record_type, source_record_key))::integer
      from supplied
    ),
    encode(
      pg_catalog.sha256(
        convert_to(
          coalesce(
            string_agg(line, E'\n' order by convert_to(line, 'UTF8')),
            ''
          ),
          'UTF8'
        )
      ),
      'hex'
    )
  into v_record_count, v_distinct_count, v_computed_fingerprint
  from canonical;

  if v_record_count <> v_distinct_count then
    raise exception 'O snapshot Transferegov contem chaves repetidas.';
  end if;
  if v_computed_fingerprint <> p_snapshot_fingerprint then
    raise exception 'A impressao do snapshot Transferegov diverge da evidencia.';
  end if;

  select run.source_endpoint_id, run.status
  into v_endpoint_id, v_run_status
  from source.collection_runs as run
  join source.source_endpoints as endpoint
    on endpoint.id = run.source_endpoint_id
  join source.data_sources as data_source
    on data_source.id = endpoint.data_source_id
  where run.id = p_collection_run_id
    and data_source.slug = 'transferegov-parcerias'
    and endpoint.slug = 'propostas-barreiras'
  for update of run;

  if v_endpoint_id is null then
    raise exception 'A execucao principal do Transferegov nao foi localizada.';
  end if;
  if v_run_status not in ('running', 'succeeded') then
    raise exception 'A execucao Transferegov nao aceita um novo snapshot.';
  end if;

  select manifest.id
  into v_snapshot_id
  from source.transferegov_snapshot_manifests as manifest
  where manifest.collection_run_id = p_collection_run_id
    and manifest.fiscal_year = p_fiscal_year
  for update;

  if v_snapshot_id is not null then
    if not exists (
      select 1
      from source.transferegov_snapshot_manifests as manifest
      where manifest.id = v_snapshot_id
        and manifest.record_count = v_record_count
        and manifest.snapshot_fingerprint = p_snapshot_fingerprint
    ) or exists (
      with supplied as (
        select
          item ->> 'record_type' as record_type,
          item ->> 'source_record_key' as source_record_key,
          item ->> 'payload_sha256' as payload_sha256
        from jsonb_array_elements(p_records) as input(item)
      ), differences as (
        (
          select record_type, source_record_key, payload_sha256 from supplied
          except
          select record_type, source_record_key, payload_sha256
          from source.transferegov_snapshot_records
          where snapshot_id = v_snapshot_id
        )
        union all
        (
          select record_type, source_record_key, payload_sha256
          from source.transferegov_snapshot_records
          where snapshot_id = v_snapshot_id
          except
          select record_type, source_record_key, payload_sha256 from supplied
        )
      )
      select 1 from differences
    ) then
      raise exception 'Conflito de idempotencia no snapshot Transferegov.';
    end if;
    return v_snapshot_id;
  end if;

  v_target_status := case
    when v_run_status = 'succeeded' then 'active'
    else 'pending'
  end;

  if v_target_status = 'active' then
    perform 1
    from source.source_endpoints
    where id = v_endpoint_id
    for update;
    update source.transferegov_snapshot_manifests
    set status = 'superseded', superseded_at = statement_timestamp()
    where source_endpoint_id = v_endpoint_id
      and fiscal_year = p_fiscal_year
      and status = 'active';
  end if;

  insert into source.transferegov_snapshot_manifests (
    source_endpoint_id,
    collection_run_id,
    fiscal_year,
    status,
    record_count,
    snapshot_fingerprint,
    activated_at
  )
  values (
    v_endpoint_id,
    p_collection_run_id,
    p_fiscal_year,
    v_target_status,
    v_record_count,
    p_snapshot_fingerprint,
    case when v_target_status = 'active' then statement_timestamp() end
  )
  returning id into v_snapshot_id;

  with supplied as (
    select
      item ->> 'record_type' as record_type,
      item ->> 'source_record_key' as source_record_key,
      item ->> 'payload_sha256' as payload_sha256
    from jsonb_array_elements(p_records) as input(item)
  )
  insert into source.transferegov_snapshot_records (
    snapshot_id,
    raw_record_id,
    record_type,
    source_record_key,
    payload_sha256
  )
  select
    v_snapshot_id,
    matched.id,
    supplied.record_type,
    supplied.source_record_key,
    supplied.payload_sha256
  from supplied
  join lateral (
    select record.id
    from raw.raw_records as record
    where record.record_type = supplied.record_type
      and record.source_record_key = supplied.source_record_key
      and record.payload_sha256 = supplied.payload_sha256
    order by record.collected_at desc, record.id desc
    limit 1
  ) as matched on true;

  get diagnostics v_inserted_count = row_count;
  if v_inserted_count <> v_record_count then
    raise exception 'Nem toda evidencia do snapshot existe no acervo bruto.';
  end if;

  return v_snapshot_id;
end;
$function$;

revoke all on function
  source.stage_transferegov_snapshot(uuid, smallint, jsonb, text)
from public, anon, authenticated;
grant execute on function
  source.stage_transferegov_snapshot(uuid, smallint, jsonb, text)
to collector_worker;

create function source.finalize_transferegov_snapshots_for_run()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  pending_manifest record;
begin
  if new.status = 'succeeded' and old.status is distinct from new.status then
    for pending_manifest in
      select manifest.id, manifest.source_endpoint_id, manifest.fiscal_year
      from source.transferegov_snapshot_manifests as manifest
      where manifest.collection_run_id = new.id
        and manifest.status = 'pending'
      order by manifest.fiscal_year
      for update
    loop
      perform 1
      from source.source_endpoints
      where id = pending_manifest.source_endpoint_id
      for update;
      update source.transferegov_snapshot_manifests
      set status = 'superseded', superseded_at = statement_timestamp()
      where source_endpoint_id = pending_manifest.source_endpoint_id
        and fiscal_year = pending_manifest.fiscal_year
        and status = 'active';
      update source.transferegov_snapshot_manifests
      set status = 'active', activated_at = statement_timestamp()
      where id = pending_manifest.id
        and status = 'pending';
    end loop;
  elsif new.status in (
    'partial', 'retry_scheduled', 'failed', 'dead_lettered', 'cancelled'
  ) and old.status is distinct from new.status then
    update source.transferegov_snapshot_manifests
    set status = 'abandoned'
    where collection_run_id = new.id
      and status = 'pending';
  end if;
  return new;
end;
$function$;

revoke all on function source.finalize_transferegov_snapshots_for_run()
from public, anon, authenticated, collector_worker;

create trigger collection_runs_finalize_transferegov_snapshots
after update of status on source.collection_runs
for each row execute function source.finalize_transferegov_snapshots_for_run();

-- Semear o estado publicado antes de substituir a view. Assim a migration nao
-- cria janela vazia entre deploy e a primeira coleta com o novo contrato.
create temporary table transferegov_snapshot_seed_records on commit drop as
with latest as (
  select latest_record.*, record.payload_sha256
  from territory.latest_transferegov_records as latest_record
  join raw.raw_records as record on record.id = latest_record.raw_record_id
), proposals as (
  select
    (latest.payload ->> 'ano_proposta')::smallint as fiscal_year,
    latest.payload ->> 'id_proposta' as proposal_id,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  where latest.record_type = 'transferegov_proposta'
    and latest.payload ->> 'ano_proposta' ~ '^[0-9]{4}$'
    and latest.payload ->> 'id_proposta' ~ '^[0-9]+$'
), distributions as (
  select
    proposal.fiscal_year,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  join proposals as proposal
    on proposal.proposal_id = latest.payload ->> 'id_proposta'
  where latest.record_type = 'transferegov_distribuicao_recurso'
), partnerships as (
  select
    proposal.fiscal_year,
    latest.payload ->> 'id_parceria' as partnership_id,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  join proposals as proposal
    on proposal.proposal_id = latest.payload ->> 'id_proposta'
  where latest.record_type = 'transferegov_parceria'
    and latest.payload ->> 'id_parceria' ~ '^[0-9]+$'
), commitments as (
  select
    partnership.fiscal_year,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  join partnerships as partnership
    on partnership.partnership_id = latest.payload ->> 'id_parceria'
  where latest.record_type = 'transferegov_empenho'
), payable_documents as (
  select
    partnership.fiscal_year,
    latest.payload ->> 'id_documento_habil' as document_id,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  join partnerships as partnership
    on partnership.partnership_id = latest.payload ->> 'id_parceria'
  where latest.record_type = 'transferegov_documento_habil'
    and latest.payload ->> 'id_documento_habil' ~ '^[0-9]+$'
), payment_records as (
  select
    document.fiscal_year,
    latest.raw_record_id,
    latest.record_type,
    latest.source_record_key,
    latest.payload_sha256
  from latest
  join payable_documents as document
    on document.document_id = latest.payload ->> 'id_documento_habil'
  where latest.record_type in (
    'transferegov_ordem_pagamento',
    'transferegov_ordem_bancaria'
  )
)
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from proposals
union all
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from distributions
union all
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from partnerships
union all
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from commitments
union all
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from payable_documents
union all
select fiscal_year, raw_record_id, record_type, source_record_key, payload_sha256
from payment_records;

do $block$
declare
  seed record;
  seed_fingerprint text;
begin
  for seed in
    with endpoint as (
      select source_endpoint.id
      from source.source_endpoints as source_endpoint
      join source.data_sources as data_source
        on data_source.id = source_endpoint.data_source_id
      where data_source.slug = 'transferegov-parcerias'
        and source_endpoint.slug = 'propostas-barreiras'
    )
    select
      partition.collection_run_id,
      extract(year from partition.period_start)::smallint as fiscal_year,
      coalesce(
        jsonb_agg(
          jsonb_build_object(
            'record_type', seed_record.record_type,
            'source_record_key', seed_record.source_record_key,
            'payload_sha256', seed_record.payload_sha256
          )
          order by seed_record.record_type, seed_record.source_record_key
        ) filter (where seed_record.raw_record_id is not null),
        '[]'::jsonb
      ) as records
    from source.collection_partitions as partition
    join endpoint on endpoint.id = partition.source_endpoint_id
    left join pg_temp.transferegov_snapshot_seed_records as seed_record
      on seed_record.fiscal_year =
        extract(year from partition.period_start)::smallint
    where partition.partition_key =
      'fiscal-year:' || extract(year from partition.period_start)::integer::text
      and partition.status in ('complete', 'empty')
      and partition.collection_run_id is not null
      and partition.period_start >= date '2021-01-01'
    group by partition.collection_run_id, partition.period_start
  loop
    with supplied as (
      select
        (item ->> 'record_type') || chr(31) ||
        (item ->> 'source_record_key') || chr(31) ||
        (item ->> 'payload_sha256') as line
      from jsonb_array_elements(seed.records) as input(item)
    )
    select encode(
      pg_catalog.sha256(
        convert_to(
          coalesce(
            string_agg(line, E'\n' order by convert_to(line, 'UTF8')),
            ''
          ),
          'UTF8'
        )
      ),
      'hex'
    )
    into seed_fingerprint
    from supplied;

    perform source.stage_transferegov_snapshot(
      seed.collection_run_id,
      seed.fiscal_year,
      seed.records,
      seed_fingerprint
    );
  end loop;
end;
$block$;

create or replace view territory.latest_transferegov_records
with (security_barrier = true)
as
select
  record.id as raw_record_id,
  record.raw_artifact_id,
  record.source_record_key,
  record.record_type,
  record.payload,
  record.collected_at
from source.transferegov_snapshot_manifests as manifest
join source.transferegov_snapshot_records as member
  on member.snapshot_id = manifest.id
join raw.raw_records as record
  on record.id = member.raw_record_id
 and record.record_type = member.record_type
 and record.source_record_key = member.source_record_key
 and record.payload_sha256 = member.payload_sha256
where manifest.status = 'active';

create or replace function api.get_public_transferegov_current_snapshot_evidence()
returns table (
  fiscal_year smallint,
  coverage_status text,
  record_count integer,
  snapshot_fingerprint text,
  last_attempted_at timestamptz,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
with endpoint as (
  select source_endpoint.id, source_endpoint.base_url
  from source.source_endpoints as source_endpoint
  join source.data_sources as data_source
    on data_source.id = source_endpoint.data_source_id
  where data_source.slug = 'transferegov-parcerias'
    and source_endpoint.slug = 'propostas-barreiras'
), current_partitions as (
  select
    partition.collection_run_id,
    extract(year from partition.period_start)::smallint as fiscal_year,
    partition.status,
    partition.last_attempted_at
  from source.collection_partitions as partition
  join endpoint on endpoint.id = partition.source_endpoint_id
  where partition.partition_key =
    'fiscal-year:' || extract(year from partition.period_start)::integer::text
    and partition.status in ('complete', 'empty')
    and partition.period_start >= date '2021-01-01'
)
select
  partition.fiscal_year,
  partition.status::text as coverage_status,
  manifest.record_count,
  manifest.snapshot_fingerprint,
  partition.last_attempted_at,
  endpoint.base_url as source_url,
  'transferegov-current-snapshot/1.1.0'::text as methodology_version
from current_partitions as partition
cross join endpoint
join source.transferegov_snapshot_manifests as manifest
  on manifest.source_endpoint_id = endpoint.id
 and manifest.collection_run_id = partition.collection_run_id
 and manifest.fiscal_year = partition.fiscal_year
 and manifest.status = 'active'
where (partition.status = 'empty' and manifest.record_count = 0)
   or (partition.status = 'complete' and manifest.record_count > 0)
order by partition.fiscal_year;
$function$;

revoke all on function
  api.get_public_transferegov_current_snapshot_evidence()
from public;
grant execute on function
  api.get_public_transferegov_current_snapshot_evidence()
to anon, authenticated;

comment on table source.transferegov_snapshot_manifests is
  'Versoes anuais do conjunto normalizado atual do Transferegov; historico bruto permanece imutavel.';
comment on table source.transferegov_snapshot_records is
  'Membership exato de registros brutos em cada snapshot anual do Transferegov.';
comment on function
  source.stage_transferegov_snapshot(uuid, smallint, jsonb, text) is
  'Valida e prepara a composicao exata do snapshot antes do sucesso da coleta principal.';
comment on function
  api.get_public_transferegov_current_snapshot_evidence() is
  'Expõe apenas contagem e SHA-256 do snapshot anual ativo ligado a coleta concluida.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:transferegov-active-snapshot-membership',
  'methodology.transferegov_active_snapshot_membership_created',
  'source.transferegov_snapshot_manifests',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'transferegov-current-snapshot/1.1.0',
    'publication_scope', 'active snapshot membership only',
    'raw_history_deleted', false
  ),
  jsonb_build_object(
    'publishes_payloads', false,
    'publishes_source_record_keys', false,
    'public_projection_seeded_before_view_replacement', true
  )
);

notify pgrst, 'reload schema';

commit;
