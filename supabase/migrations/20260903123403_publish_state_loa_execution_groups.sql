begin;

set local statement_timeout = '120s';
set local lock_timeout = '5s';

create table territory.bahia_state_loa_execution_group_snapshot (
  fiscal_year smallint not null,
  author_external_code text not null,
  author_key text not null,
  author_name text not null,
  agency_code text not null,
  budget_unit_code text not null,
  action_code text not null,
  amendment_count integer not null check (amendment_count >= 2),
  amendment_numbers text[] not null,
  authorized_total numeric(20,2) not null,
  execution_code text not null,
  initial_budget_amount numeric(20,2) not null,
  current_budget_amount numeric(20,2) not null,
  committed_amount numeric(20,2) not null,
  liquidated_amount numeric(20,2) not null,
  paid_amount numeric(20,2) not null,
  execution_source_url text not null,
  execution_source_artifact_sha256 text not null
    check (execution_source_artifact_sha256 ~ '^[0-9a-f]{64}$'),
  execution_evidence_sha256 text not null
    check (execution_evidence_sha256 ~ '^[0-9a-f]{64}$'),
  execution_source_collected_at timestamptz not null,
  refreshed_at timestamptz not null default statement_timestamp(),
  primary key (
    fiscal_year,
    author_external_code,
    agency_code,
    budget_unit_code,
    action_code
  ),
  check (cardinality(amendment_numbers) = amendment_count)
);

alter table territory.bahia_state_loa_execution_group_snapshot
  enable row level security;
alter table territory.bahia_state_loa_execution_group_snapshot
  force row level security;

revoke all on table
  territory.bahia_state_loa_execution_group_snapshot
from public, anon, authenticated;

create function territory.refresh_bahia_state_loa_execution_group_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  refreshed_rows integer;
begin
  delete from territory.bahia_state_loa_execution_group_snapshot;

  insert into territory.bahia_state_loa_execution_group_snapshot (
    fiscal_year,
    author_external_code,
    author_key,
    author_name,
    agency_code,
    budget_unit_code,
    action_code,
    amendment_count,
    amendment_numbers,
    authorized_total,
    execution_code,
    initial_budget_amount,
    current_budget_amount,
    committed_amount,
    liquidated_amount,
    paid_amount,
    execution_source_url,
    execution_source_artifact_sha256,
    execution_evidence_sha256,
    execution_source_collected_at
  )
  with eligible_groups as (
    select
      reconciliation.fiscal_year,
      reconciliation.author_external_code,
      min(reconciliation.author_key) as author_key,
      min(reconciliation.author_name) as author_name,
      reconciliation.agency_code,
      reconciliation.budget_unit_code,
      reconciliation.action_code,
      count(*)::integer as amendment_count,
      array_agg(
        distinct reconciliation.amendment_number
        order by reconciliation.amendment_number
      ) as amendment_numbers,
      sum(reconciliation.authorized_amount)::numeric(20,2)
        as authorized_total
    from territory.bahia_state_loa_execution_reconciliation_snapshot
      as reconciliation
    where reconciliation.reconciliation_status =
      'blocked_non_unique_loa_key'
    group by
      reconciliation.fiscal_year,
      reconciliation.author_external_code,
      reconciliation.agency_code,
      reconciliation.budget_unit_code,
      reconciliation.action_code
    having count(*) >= 2
      and count(*) = max(reconciliation.loa_scope_occurrences)
      and max(reconciliation.execution_occurrences) = 1
      and count(distinct reconciliation.amendment_number) = count(*)
      and count(distinct reconciliation.author_key) = 1
  ), execution_job_years as (
    select
      result.extraction_job_id,
      (result.result_payload ->> 'fiscal_year')::smallint as fiscal_year,
      row_number() over (
        partition by (result.result_payload ->> 'fiscal_year')::smallint
        order by
          max((result.result_payload ->> 'source_collected_at')::timestamptz)
            desc,
          max(result.created_at) desc,
          result.extraction_job_id desc
      ) as snapshot_rank
    from raw.extraction_results as result
    join raw.extraction_jobs as job
      on job.id = result.extraction_job_id
     and job.status = 'succeeded'
    where result.candidate_type = 'bahia_state_execution_aggregate'
      and result.extractor_version = 'bahia-state-execution-aggregate/1.0.0'
      and result.validator_version =
        'bahia-state-execution-deterministic/1.0.0'
      and result.validation_status = 'valid'
      and result.validation_errors = '[]'::jsonb
      and result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
      and result.result_payload ->> 'source_collected_at' is not null
    group by
      result.extraction_job_id,
      (result.result_payload ->> 'fiscal_year')::smallint
  ), execution_rows as (
    select result.result_payload as payload
    from raw.extraction_results as result
    join execution_job_years as snapshot
      on snapshot.extraction_job_id = result.extraction_job_id
     and snapshot.fiscal_year =
       (result.result_payload ->> 'fiscal_year')::smallint
     and snapshot.snapshot_rank = 1
    where result.candidate_type = 'bahia_state_execution_aggregate'
      and result.extractor_version = 'bahia-state-execution-aggregate/1.0.0'
      and result.validator_version =
        'bahia-state-execution-deterministic/1.0.0'
      and result.validation_status = 'valid'
      and result.validation_errors = '[]'::jsonb
      and nullif(btrim(result.result_payload ->> 'execution_code'), '')
        is not null
      and result.result_payload ->> 'initial_budget_amount'
        ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
      and result.result_payload ->> 'current_budget_amount'
        ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
      and result.result_payload ->> 'committed_amount'
        ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
      and result.result_payload ->> 'liquidated_amount'
        ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
      and result.result_payload ->> 'paid_amount'
        ~ '^-?[0-9]{1,18}(?:[.][0-9]{1,2})?$'
      and result.result_payload ->> 'source_url' ~ '^https://'
      and result.result_payload ->> 'source_artifact_sha256'
        ~ '^[0-9a-f]{64}$'
      and result.result_payload ->> 'evidence_sha256' ~ '^[0-9a-f]{64}$'
  ), execution_groups as (
    select
      (payload ->> 'fiscal_year')::smallint as fiscal_year,
      btrim(payload ->> 'author_external_code') as author_external_code,
      btrim(payload ->> 'agency_code') as agency_code,
      btrim(payload ->> 'budget_unit_code') as budget_unit_code,
      btrim(payload ->> 'action_code') as action_code,
      count(*)::integer as occurrence_count,
      max(payload ->> 'execution_code') as execution_code,
      max((payload ->> 'initial_budget_amount')::numeric(20,2))
        as initial_budget_amount,
      max((payload ->> 'current_budget_amount')::numeric(20,2))
        as current_budget_amount,
      max((payload ->> 'committed_amount')::numeric(20,2))
        as committed_amount,
      max((payload ->> 'liquidated_amount')::numeric(20,2))
        as liquidated_amount,
      max((payload ->> 'paid_amount')::numeric(20,2)) as paid_amount,
      max(payload ->> 'source_url') as source_url,
      max(payload ->> 'source_artifact_sha256') as source_artifact_sha256,
      max(payload ->> 'evidence_sha256') as evidence_sha256,
      max((payload ->> 'source_collected_at')::timestamptz)
        as source_collected_at
    from execution_rows
    group by
      payload ->> 'fiscal_year',
      btrim(payload ->> 'author_external_code'),
      btrim(payload ->> 'agency_code'),
      btrim(payload ->> 'budget_unit_code'),
      btrim(payload ->> 'action_code')
    having count(*) = 1
  )
  select
    eligible.fiscal_year,
    eligible.author_external_code,
    eligible.author_key,
    eligible.author_name,
    eligible.agency_code,
    eligible.budget_unit_code,
    eligible.action_code,
    eligible.amendment_count,
    eligible.amendment_numbers,
    eligible.authorized_total,
    execution.execution_code,
    execution.initial_budget_amount,
    execution.current_budget_amount,
    execution.committed_amount,
    execution.liquidated_amount,
    execution.paid_amount,
    execution.source_url,
    execution.source_artifact_sha256,
    execution.evidence_sha256,
    execution.source_collected_at
  from eligible_groups as eligible
  join execution_groups as execution
    on execution.fiscal_year = eligible.fiscal_year
   and execution.author_external_code = eligible.author_external_code
   and execution.agency_code = eligible.agency_code
   and execution.budget_unit_code = eligible.budget_unit_code
   and execution.action_code = eligible.action_code
   and execution.occurrence_count = 1;

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
    'reconciliation.group_snapshot_refreshed',
    'territory.bahia_state_loa_execution_group_snapshot',
    gen_random_uuid(),
    jsonb_build_object(
      'row_count', refreshed_rows,
      'methodology_version', 'bahia-state-loa-execution-group/1.0.0'
    ),
    jsonb_build_object(
      'values_allocated_to_individual_amendments', false,
      'requires_complete_barreiras_group', true
    )
  );

  return refreshed_rows;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_loa_execution_group_snapshot()
from public, anon, authenticated;
grant execute on function
  territory.refresh_bahia_state_loa_execution_group_snapshot()
to collector_worker;

comment on table territory.bahia_state_loa_execution_group_snapshot is
  'Execucao agregada somente para chaves cujas emendas da LOA pertencem integralmente a Barreiras; os valores nao sao repartidos por emenda.';

create function api.get_public_bahia_state_loa_execution_groups(
  fiscal_year_filter smallint,
  page_size integer default 50
)
returns table (
  fiscal_year smallint,
  author_external_code text,
  author_key text,
  author_name text,
  agency_code text,
  budget_unit_code text,
  action_code text,
  amendment_count integer,
  amendment_numbers text[],
  authorized_total numeric(20,2),
  execution_code text,
  initial_budget_amount numeric(20,2),
  current_budget_amount numeric(20,2),
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
begin
  if fiscal_year_filter is null
    or fiscal_year_filter < 2022
    or fiscal_year_filter > current_fiscal_year
  then
    raise exception 'ano dos grupos estaduais invalido'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 100 then
    raise exception 'limite dos grupos estaduais invalido'
      using errcode = '22023';
  end if;

  return query
  select
    snapshot.fiscal_year,
    snapshot.author_external_code,
    snapshot.author_key,
    snapshot.author_name,
    snapshot.agency_code,
    snapshot.budget_unit_code,
    snapshot.action_code,
    snapshot.amendment_count,
    snapshot.amendment_numbers,
    snapshot.authorized_total,
    snapshot.execution_code,
    snapshot.initial_budget_amount,
    snapshot.current_budget_amount,
    snapshot.committed_amount,
    snapshot.liquidated_amount,
    snapshot.paid_amount,
    snapshot.execution_source_url,
    snapshot.execution_source_artifact_sha256,
    snapshot.execution_evidence_sha256,
    snapshot.execution_source_collected_at,
    'bahia-state-loa-execution-group/1.0.0'::text
  from territory.bahia_state_loa_execution_group_snapshot as snapshot
  where snapshot.fiscal_year = fiscal_year_filter
  order by
    snapshot.authorized_total desc,
    snapshot.author_name,
    snapshot.agency_code,
    snapshot.budget_unit_code,
    snapshot.action_code
  limit page_size;
end;
$$;

revoke all on function
  api.get_public_bahia_state_loa_execution_groups(smallint, integer)
from public;
grant execute on function
  api.get_public_bahia_state_loa_execution_groups(smallint, integer)
to anon, authenticated;

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
  'migration:publish-state-loa-execution-groups',
  'reconciliation.group_projection_created',
  'territory.bahia_state_loa_execution_group_snapshot',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'bahia-state-loa-execution-group/1.0.0',
    'group_values_are_not_allocated_to_individual_amendments', true
  ),
  jsonb_build_object(
    'requires_all_scope_rows_in_barreiras', true,
    'requires_one_execution_row', true,
    'public_rpc_count', 1
  )
);

notify pgrst, 'reload schema';

commit;
