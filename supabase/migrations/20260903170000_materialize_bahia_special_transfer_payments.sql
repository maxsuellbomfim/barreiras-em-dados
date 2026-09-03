begin;

set local statement_timeout = '120s';
set local lock_timeout = '5s';

-- Copy the canonical live view definition before moving the stable name to an
-- indexed snapshot. Creditor identifiers never enter this projection.
do $$
declare
  live_definition text;
begin
  select pg_catalog.pg_get_viewdef(
    'territory.latest_bahia_special_transfer_payment_candidates'::regclass,
    true
  )
  into live_definition;
  execute
    'create view territory.latest_bahia_special_transfer_payment_candidates_live '
    || 'with (security_barrier = true) as '
    || live_definition;
end;
$$;

revoke all on territory.latest_bahia_special_transfer_payment_candidates_live
from public, anon, authenticated;

create table territory.bahia_special_transfer_payment_snapshot
as
select *
from territory.latest_bahia_special_transfer_payment_candidates_live
with no data;

alter table territory.bahia_special_transfer_payment_snapshot
  add primary key (payment_id);

create index bahia_special_transfer_payment_snapshot_fiscal_date_idx
  on territory.bahia_special_transfer_payment_snapshot (
    fiscal_year desc,
    payment_date desc,
    payment_id
  );

alter table territory.bahia_special_transfer_payment_snapshot
  enable row level security;
alter table territory.bahia_special_transfer_payment_snapshot
  force row level security;

revoke all on table territory.bahia_special_transfer_payment_snapshot
from public, anon, authenticated;

create function territory.refresh_bahia_special_transfer_payment_snapshot()
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
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'territory.bahia_special_transfer_payment_snapshot',
      0
    )
  );

  select
    count(*)::integer,
    coalesce(
      jsonb_agg(
        to_jsonb(source_row)
        order by source_row.payment_id
      ),
      '[]'::jsonb
    )::text
  into live_rows, live_payload
  from territory.latest_bahia_special_transfer_payment_candidates_live
    as source_row;

  live_manifest := encode(
    pg_catalog.sha256(convert_to(live_payload, 'UTF8')),
    'hex'
  );

  delete from territory.bahia_special_transfer_payment_snapshot;

  insert into territory.bahia_special_transfer_payment_snapshot
  select *
  from territory.latest_bahia_special_transfer_payment_candidates_live;

  get diagnostics refreshed_rows = row_count;

  select coalesce(
    jsonb_agg(
      to_jsonb(snapshot_row)
      order by snapshot_row.payment_id
    ),
    '[]'::jsonb
  )::text
  into snapshot_payload
  from territory.bahia_special_transfer_payment_snapshot as snapshot_row;

  snapshot_manifest := encode(
    pg_catalog.sha256(convert_to(snapshot_payload, 'UTF8')),
    'hex'
  );

  if refreshed_rows <> live_rows
     or snapshot_manifest is distinct from live_manifest
  then
    raise exception
      'Snapshot de pagamentos estaduais especiais divergiu da fonte canonica: fonte=%, snapshot=%',
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
    'worker:bahia-special-transfers',
    'source_snapshot.refreshed',
    'territory.bahia_special_transfer_payment_snapshot',
    gen_random_uuid(),
    jsonb_build_object(
      'row_count', refreshed_rows,
      'content_sha256', snapshot_manifest,
      'methodology_version',
      'bahia-special-transfer-payment-snapshot/1.0.0'
    ),
    jsonb_build_object(
      'source_projection',
      'territory.latest_bahia_special_transfer_payment_candidates_live',
      'raw_json_recomputed_per_public_request', false
    )
  );

  return refreshed_rows;
end;
$$;

grant usage on schema territory to collector_worker;
revoke all on function
  territory.refresh_bahia_special_transfer_payment_snapshot()
from public, anon, authenticated;
grant execute on function
  territory.refresh_bahia_special_transfer_payment_snapshot()
to collector_worker;

-- This stable private name keeps its existing OID. Only the source changes:
-- public RPCs continue to use the same contracts.
create or replace view territory.latest_bahia_special_transfer_payment_candidates
with (security_barrier = true)
as
select *
from territory.bahia_special_transfer_payment_snapshot;

revoke all on territory.latest_bahia_special_transfer_payment_candidates
from public, anon, authenticated;

-- The federal-link view already depends on the stable payment projection, so
-- it follows the snapshot without materializing a crosswalk or CGU relation.
comment on view territory.latest_bahia_special_transfer_payment_candidates_live is
  'Projecao canonica privada sobre extracoes validadas; usada somente para atualizar o snapshot de pagamentos estaduais especiais.';
comment on table territory.bahia_special_transfer_payment_snapshot is
  'Snapshot privado e indexado dos pagamentos estaduais especiais territorialmente observados; sem identificadores de credores.';
comment on function
  territory.refresh_bahia_special_transfer_payment_snapshot() is
  'Atualiza atomicamente o snapshot de pagamentos estaduais especiais; restrita ao worker e protegida por lock transacional.';

select territory.refresh_bahia_special_transfer_payment_snapshot();

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
  'migration:materialize-bahia-special-transfer-payments',
  'performance.special_transfer_payment_source_materialized',
  'territory.bahia_special_transfer_payment_snapshot',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'bahia-special-transfer-payment-snapshot/1.0.0',
    'public_contract_changed', false
  ),
  jsonb_build_object(
    'raw_source_view_preserved', true,
    'refresh_role', 'collector_worker',
    'crosswalk_materialized', false,
    'personal_identifiers_exposed', false
  )
);

notify pgrst, 'reload schema';

commit;
