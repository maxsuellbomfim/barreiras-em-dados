begin;

set local statement_timeout = '120s';
set local lock_timeout = '5s';

-- Rename the existing relation instead of rebuilding it. PostgreSQL preserves
-- its OID, so the private reconciliation view keeps following the live/raw
-- projection while callers that resolve the stable name below receive the
-- indexed snapshot.
alter view territory.bahia_state_loa_amendments
  rename to bahia_state_loa_amendments_live;

revoke all on territory.bahia_state_loa_amendments_live
from public, anon, authenticated;

create table territory.bahia_state_loa_amendment_snapshot
as
select *
from territory.bahia_state_loa_amendments_live
with no data;

alter table territory.bahia_state_loa_amendment_snapshot
  add primary key (origin_extraction_result_id);

create unique index bahia_state_loa_amendment_snapshot_evidence_idx
  on territory.bahia_state_loa_amendment_snapshot (
    source_artifact_sha256,
    evidence_sha256
  );

create index bahia_state_loa_amendment_snapshot_year_author_idx
  on territory.bahia_state_loa_amendment_snapshot (
    fiscal_year desc,
    author_key,
    authorized_amount desc,
    amendment_number,
    page_number
  );

alter table territory.bahia_state_loa_amendment_snapshot
  enable row level security;
alter table territory.bahia_state_loa_amendment_snapshot
  force row level security;

revoke all on table territory.bahia_state_loa_amendment_snapshot
from public, anon, authenticated;

create function territory.refresh_bahia_state_loa_amendment_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  live_rows integer;
  refreshed_rows integer;
  live_payload text;
  snapshot_payload text;
  live_manifest text;
  snapshot_manifest text;
begin
  select
    count(*)::integer,
    coalesce(
      jsonb_agg(
        to_jsonb(source_row)
        order by source_row.origin_extraction_result_id
      ),
      '[]'::jsonb
    )::text
  into live_rows, live_payload
  from territory.bahia_state_loa_amendments_live as source_row;

  if to_regprocedure('extensions.digest(bytea,text)') is not null then
    execute
      'select encode(extensions.digest(convert_to($1, ''UTF8''), ''sha256''), ''hex'')'
      into live_manifest
      using live_payload;
  else
    execute
      'select encode(public.digest(convert_to($1, ''UTF8''), ''sha256''), ''hex'')'
      into live_manifest
      using live_payload;
  end if;

  delete from territory.bahia_state_loa_amendment_snapshot;

  insert into territory.bahia_state_loa_amendment_snapshot
  select *
  from territory.bahia_state_loa_amendments_live;

  get diagnostics refreshed_rows = row_count;

  select coalesce(
    jsonb_agg(
      to_jsonb(snapshot_row)
      order by snapshot_row.origin_extraction_result_id
    ),
    '[]'::jsonb
  )::text
  into snapshot_payload
  from territory.bahia_state_loa_amendment_snapshot as snapshot_row;

  if to_regprocedure('extensions.digest(bytea,text)') is not null then
    execute
      'select encode(extensions.digest(convert_to($1, ''UTF8''), ''sha256''), ''hex'')'
      into snapshot_manifest
      using snapshot_payload;
  else
    execute
      'select encode(public.digest(convert_to($1, ''UTF8''), ''sha256''), ''hex'')'
      into snapshot_manifest
      using snapshot_payload;
  end if;

  if refreshed_rows <> live_rows
     or snapshot_manifest is distinct from live_manifest then
    raise exception
      'Snapshot da LOA estadual divergiu da fonte canonica: fonte=%, snapshot=%',
      live_rows,
      refreshed_rows;
  end if;

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
    'source_snapshot.refreshed',
    'territory.bahia_state_loa_amendment_snapshot',
    gen_random_uuid(),
    jsonb_build_object(
      'row_count', refreshed_rows,
      'content_sha256', snapshot_manifest,
      'methodology_version',
      'bahia-state-loa-amendment-snapshot/1.0.0'
    ),
    jsonb_build_object(
      'source_projection',
      'territory.bahia_state_loa_amendments_live',
      'raw_json_recomputed_per_public_request', false
    )
  );

  return refreshed_rows;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_loa_amendment_snapshot()
from public, anon, authenticated;
grant execute on function
  territory.refresh_bahia_state_loa_amendment_snapshot()
to collector_worker;

comment on view territory.bahia_state_loa_amendments_live is
  'Projecao canonica privada sobre extracoes validadas da LOA; usada somente para atualizar o snapshot.';
comment on table territory.bahia_state_loa_amendment_snapshot is
  'Snapshot privado e indexado das emendas estaduais autorizadas para Barreiras; fonte das leituras publicas.';
comment on function
  territory.refresh_bahia_state_loa_amendment_snapshot() is
  'Atualiza atomicamente a fonte normalizada da LOA antes da reconciliacao; restrita ao worker.';

select territory.refresh_bahia_state_loa_amendment_snapshot();

create view territory.bahia_state_loa_amendments
with (security_barrier = true)
as
select
  snapshot.origin_extraction_result_id,
  snapshot.origin_extraction_job_id,
  snapshot.origin_raw_artifact_id,
  snapshot.fiscal_year,
  snapshot.amendment_number,
  snapshot.author_external_code,
  snapshot.author_name,
  snapshot.author_key,
  snapshot.authorized_amount,
  snapshot.official_description,
  snapshot.annex_code,
  snapshot.budget_unit_code,
  snapshot.agency_code,
  snapshot.action_code,
  snapshot.page_number,
  snapshot.evidence_text,
  snapshot.financial_stage,
  snapshot.source_url,
  snapshot.source_artifact_sha256,
  snapshot.evidence_sha256,
  snapshot.created_at
from territory.bahia_state_loa_amendment_snapshot as snapshot;

revoke all on territory.bahia_state_loa_amendments
from public, anon, authenticated;

comment on view territory.bahia_state_loa_amendments is
  'Projecao privada estavel das emendas autorizadas para Barreiras; le somente o snapshot normalizado.';

create or replace function territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  refreshed_rows integer;
begin
  perform territory.refresh_bahia_state_loa_amendment_snapshot();

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
      'source_snapshot_refreshed_first', true,
      'public_values_require_unique_match', true
    )
  );

  return refreshed_rows;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
from public, anon, authenticated;
grant execute on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()
to collector_worker;

comment on function
  territory.refresh_bahia_state_loa_execution_reconciliation_snapshot() is
  'Atualiza primeiro a fonte normalizada e depois reconstroi a reconciliacao estadual na mesma transacao.';

select territory.refresh_bahia_state_loa_execution_reconciliation_snapshot();
select territory.refresh_bahia_state_loa_execution_group_snapshot();

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
  'migration:materialize-bahia-state-loa-source',
  'performance.state_loa_source_materialized',
  'territory.bahia_state_loa_amendment_snapshot',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'bahia-state-loa-amendment-snapshot/1.0.0',
    'public_contract_changed', false
  ),
  jsonb_build_object(
    'raw_source_view_preserved', true,
    'refresh_role', 'collector_worker'
  )
);

notify pgrst, 'reload schema';

commit;
