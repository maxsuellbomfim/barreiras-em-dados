begin;

set local statement_timeout = '120s';
set local lock_timeout = '5s';

create table territory.bahia_state_loa_execution_reconciliation_snapshot
as
select *
from territory.bahia_state_loa_execution_reconciliation
with no data;

alter table territory.bahia_state_loa_execution_reconciliation_snapshot
  add primary key (origin_extraction_result_id);

create index bahia_state_loa_execution_snapshot_year_author_idx
  on territory.bahia_state_loa_execution_reconciliation_snapshot (
    fiscal_year desc,
    author_key,
    authorized_amount desc,
    amendment_number
  );

alter table territory.bahia_state_loa_execution_reconciliation_snapshot
  enable row level security;
alter table territory.bahia_state_loa_execution_reconciliation_snapshot
  force row level security;

revoke all on table
  territory.bahia_state_loa_execution_reconciliation_snapshot
from public, anon, authenticated;

create function territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  refreshed_rows integer;
begin
  delete from territory.bahia_state_loa_execution_reconciliation_snapshot;

  insert into territory.bahia_state_loa_execution_reconciliation_snapshot
  select *
  from territory.bahia_state_loa_execution_reconciliation;

  get diagnostics refreshed_rows = row_count;

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
    'system',
    'worker:bahia-state-loa',
    'reconciliation.snapshot_refreshed',
    'territory.bahia_state_loa_execution_reconciliation_snapshot',
    gen_random_uuid(),
    jsonb_build_object(
      'row_count', refreshed_rows,
      'methodology_version',
      'bahia-state-loa-execution-reconciliation-snapshot/1.0.0'
    ),
    jsonb_build_object(
      'source_projection',
      'territory.bahia_state_loa_execution_reconciliation',
      'public_values_require_unique_match', true
    )
  );

  return refreshed_rows;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
from public, anon, authenticated;
grant usage on schema territory to collector_worker;
grant execute on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
to collector_worker;

comment on table
  territory.bahia_state_loa_execution_reconciliation_snapshot is
  'Snapshot privado da reconciliacao estadual; evita recalcular JSON bruto em cada requisicao publica.';
comment on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot() is
  'Reconstroi atomicamente a projecao estadual apos a normalizacao oficial; restrita ao worker.';

select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot();

create or replace function api.get_public_bahia_state_loa_execution(
  fiscal_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 100
)
returns table (
  fiscal_year smallint,
  amendment_number text,
  author_external_code text,
  author_key text,
  author_name text,
  authorized_amount numeric(20,2),
  official_description text,
  page_number integer,
  loa_evidence_text text,
  loa_source_url text,
  loa_source_artifact_sha256 text,
  loa_evidence_sha256 text,
  execution_status text,
  loa_scope_occurrences integer,
  execution_occurrences integer,
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  execution_source_url text,
  execution_source_artifact_sha256 text,
  execution_evidence_sha256 text,
  execution_source_collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
  normalized_author_key text := nullif(btrim(author_key_filter), '');
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2022 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null and length(normalized_author_key) > 200 then
    raise exception 'autor da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  select
    reconciliation.fiscal_year,
    reconciliation.amendment_number,
    reconciliation.author_external_code,
    reconciliation.author_key,
    reconciliation.author_name,
    reconciliation.authorized_amount,
    reconciliation.official_description,
    reconciliation.page_number,
    reconciliation.loa_evidence_text,
    reconciliation.loa_source_url,
    reconciliation.loa_source_artifact_sha256,
    reconciliation.loa_evidence_sha256,
    case reconciliation.reconciliation_status
      when 'matched_bidirectional_unique' then 'execution_confirmed'
      when 'blocked_non_unique_loa_key' then 'ambiguous_official_key'
      when 'blocked_non_unique_execution_key' then 'ambiguous_official_key'
      when 'not_found_in_execution_source'
        then 'not_found_in_execution_source'
      when 'blocked_scope_year_not_indexed'
        then 'official_link_key_unavailable'
      else 'scope_not_available'
    end as execution_status,
    reconciliation.loa_scope_occurrences,
    reconciliation.execution_occurrences,
    reconciliation.committed_amount,
    reconciliation.liquidated_amount,
    reconciliation.paid_amount,
    reconciliation.execution_source_url,
    reconciliation.execution_source_artifact_sha256,
    reconciliation.execution_evidence_sha256,
    reconciliation.execution_source_collected_at,
    'bahia-state-loa-public-execution/1.1.0'::text
  from territory.bahia_state_loa_execution_reconciliation_snapshot
    as reconciliation
  where (
    fiscal_year_filter is null
    or reconciliation.fiscal_year = fiscal_year_filter
  )
    and (
      normalized_author_key is null
      or reconciliation.author_key = normalized_author_key
    )
  order by
    reconciliation.fiscal_year desc,
    reconciliation.authorized_amount desc,
    reconciliation.author_name,
    reconciliation.amendment_number,
    reconciliation.page_number
  limit page_size;
end;
$$;

create or replace function api.get_public_bahia_state_loa_execution_summary(
  fiscal_year_filter smallint
)
returns table (
  fiscal_year smallint,
  total_amendment_count integer,
  matched_amendment_count integer,
  ambiguous_amendment_count integer,
  not_found_amendment_count integer,
  unavailable_scope_count integer,
  authorized_total numeric(20,2),
  matched_authorized_total numeric(20,2),
  committed_total numeric(20,2),
  liquidated_total numeric(20,2),
  paid_total numeric(20,2),
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
begin
  if fiscal_year_filter is null
    or fiscal_year_filter < 2022
    or fiscal_year_filter > current_fiscal_year
  then
    raise exception 'ano do resumo da execucao estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  select
    fiscal_year_filter,
    count(*)::integer,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_non_unique_loa_key',
        'blocked_non_unique_execution_key'
      )
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'not_found_in_execution_source'
    )::integer,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_scope_year_not_indexed',
        'blocked_scope_not_collected'
      )
    )::integer,
    sum(reconciliation.authorized_amount)::numeric(20,2),
    sum(reconciliation.authorized_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.committed_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.liquidated_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    sum(reconciliation.paid_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2),
    'bahia-state-loa-public-execution-summary/1.0.0'::text
  from territory.bahia_state_loa_execution_reconciliation_snapshot
    as reconciliation
  where reconciliation.fiscal_year = fiscal_year_filter
  having count(*) > 0;
end;
$$;

create or replace function
  api.get_public_bahia_state_loa_representative_contributions(
    page_size integer default 100
  )
returns table (
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  author_key text,
  author_name text,
  fiscal_year smallint,
  amendment_count integer,
  authorized_amount numeric(20,2),
  matched_amendment_count integer,
  matched_authorized_amount numeric(20,2),
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  blocked_amendment_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite das contribuicoes estaduais por representante invalido'
      using errcode = '22023';
  end if;

  return query
  with linked as (
    select
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      reconciliation.author_key,
      reconciliation.author_name,
      reconciliation.fiscal_year,
      reconciliation.amendment_number,
      reconciliation.authorized_amount,
      reconciliation.reconciliation_status,
      reconciliation.committed_amount,
      reconciliation.liquidated_amount,
      reconciliation.paid_amount
    from territory.bahia_state_loa_execution_reconciliation_snapshot
      as reconciliation
    join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
      and crosswalk.author_key = reconciliation.author_key
      and crosswalk.review_status = 'approved'
  ), grouped as (
    select
      linked.representative_source_kind,
      linked.representative_external_id,
      linked.representative_profile_url,
      linked.author_key,
      (array_agg(
        linked.author_name
        order by linked.amendment_number, linked.author_name
      ))[1] as author_name,
      linked.fiscal_year,
      count(*)::integer as amendment_count,
      sum(linked.authorized_amount)::numeric(20,2) as authorized_amount,
      count(*) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::integer as matched_amendment_count,
      sum(linked.authorized_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as matched_authorized_amount,
      sum(linked.committed_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as committed_amount,
      sum(linked.liquidated_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as liquidated_amount,
      sum(linked.paid_amount) filter (
        where linked.reconciliation_status = 'matched_bidirectional_unique'
      )::numeric(20,2) as paid_amount,
      count(*) filter (
        where linked.reconciliation_status <> 'matched_bidirectional_unique'
      )::integer as blocked_amendment_count
    from linked
    group by
      linked.representative_source_kind,
      linked.representative_external_id,
      linked.representative_profile_url,
      linked.author_key,
      linked.fiscal_year
  )
  select
    grouped.representative_source_kind,
    grouped.representative_external_id,
    grouped.representative_profile_url,
    grouped.author_key,
    grouped.author_name,
    grouped.fiscal_year,
    grouped.amendment_count,
    grouped.authorized_amount,
    grouped.matched_amendment_count,
    grouped.matched_authorized_amount,
    grouped.committed_amount,
    grouped.liquidated_amount,
    grouped.paid_amount,
    grouped.blocked_amendment_count,
    'bahia-state-loa-representative-contributions/1.0.1'::text
  from grouped
  order by
    grouped.representative_source_kind,
    grouped.representative_external_id,
    grouped.fiscal_year desc,
    grouped.author_key
  limit page_size;
end;
$$;

revoke all on function api.get_public_bahia_state_loa_execution(
  smallint, text, integer
) from public;
revoke all on function api.get_public_bahia_state_loa_execution_summary(
  smallint
) from public;
revoke all on function
  api.get_public_bahia_state_loa_representative_contributions(integer)
from public;

grant execute on function api.get_public_bahia_state_loa_execution(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_bahia_state_loa_execution_summary(
  smallint
) to anon, authenticated;
grant execute on function
  api.get_public_bahia_state_loa_representative_contributions(integer)
to anon, authenticated;

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
  'migration:fix-state-loa-public-rpc-timeout',
  'reconciliation.public_projection_materialized',
  'territory.bahia_state_loa_execution_reconciliation_snapshot',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'bahia-state-loa-execution-reconciliation-snapshot/1.0.0',
    'public_rpc_count', 3
  ),
  jsonb_build_object(
    'source_view_preserved', true,
    'raw_json_recomputed_per_request', false,
    'refresh_role', 'collector_worker'
  )
);

notify pgrst, 'reload schema';

commit;
