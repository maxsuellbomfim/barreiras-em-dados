begin;

create index if not exists bahia_state_execution_key_idx
  on raw.extraction_results (
    (result_payload ->> 'fiscal_year'),
    (result_payload ->> 'author_external_code'),
    (result_payload ->> 'agency_code'),
    (result_payload ->> 'budget_unit_code'),
    (result_payload ->> 'action_code'),
    extraction_job_id,
    created_at desc,
    id desc
  )
  where candidate_type = 'bahia_state_execution_aggregate'
    and extractor_version = 'bahia-state-execution-aggregate/1.0.0'
    and validator_version = 'bahia-state-execution-deterministic/1.0.0'
    and validation_status = 'valid';

create view territory.bahia_state_loa_execution_reconciliation
with (security_barrier = true)
as
with scope_candidates as (
  select
    result.result_payload as payload,
    row_number() over (
      partition by
        result.result_payload ->> 'source_artifact_sha256',
        result.result_payload ->> 'evidence_sha256'
      order by result.created_at desc, result.id desc
    ) as version_rank
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
   and job.status = 'succeeded'
  where result.candidate_type = 'bahia_state_loa_2026_scope_row'
    and result.extractor_version = 'bahia-state-loa-scope/1.0.0'
    and result.validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and result.result_payload ->> 'visibility' = 'private_reconciliation_scope'
    and result.result_payload ->> 'fiscal_year' = '2026'
    and result.result_payload ->> 'source_artifact_sha256' ~ '^[0-9a-f]{64}$'
    and result.result_payload ->> 'evidence_sha256' ~ '^[0-9a-f]{64}$'
    and nullif(btrim(result.result_payload ->> 'author_external_code'), '')
      is not null
    and nullif(btrim(result.result_payload ->> 'agency_code'), '') is not null
    and nullif(btrim(result.result_payload ->> 'budget_unit_code'), '')
      is not null
    and nullif(btrim(result.result_payload ->> 'action_code'), '') is not null
), scope_counts as (
  select
    payload ->> 'source_artifact_sha256' as source_artifact_sha256,
    (payload ->> 'fiscal_year')::smallint as fiscal_year,
    btrim(payload ->> 'author_external_code') as author_external_code,
    btrim(payload ->> 'agency_code') as agency_code,
    btrim(payload ->> 'budget_unit_code') as budget_unit_code,
    btrim(payload ->> 'action_code') as action_code,
    count(*)::integer as occurrence_count
  from scope_candidates
  where version_rank = 1
  group by
    payload ->> 'source_artifact_sha256',
    payload ->> 'fiscal_year',
    btrim(payload ->> 'author_external_code'),
    btrim(payload ->> 'agency_code'),
    btrim(payload ->> 'budget_unit_code'),
    btrim(payload ->> 'action_code')
), execution_job_years as (
  select
    result.extraction_job_id,
    (result.result_payload ->> 'fiscal_year')::smallint as fiscal_year,
    max((result.result_payload ->> 'source_collected_at')::timestamptz)
      as source_collected_at,
    max(result.created_at) as result_created_at,
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
    and result.validator_version = 'bahia-state-execution-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
    and result.result_payload ->> 'source_collected_at' is not null
  group by result.extraction_job_id,
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
    and result.validator_version = 'bahia-state-execution-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and nullif(btrim(result.result_payload ->> 'author_external_code'), '')
      is not null
    and nullif(btrim(result.result_payload ->> 'agency_code'), '') is not null
    and nullif(btrim(result.result_payload ->> 'budget_unit_code'), '')
      is not null
    and nullif(btrim(result.result_payload ->> 'action_code'), '') is not null
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
    and result.result_payload ->> 'source_artifact_sha256' ~ '^[0-9a-f]{64}$'
    and result.result_payload ->> 'evidence_sha256' ~ '^[0-9a-f]{64}$'
), execution_counts as (
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
    max(payload ->> 'evidence_text') as evidence_text,
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
), reconciled as (
  select
    amendment.*,
    coalesce(scope.occurrence_count, 0) as loa_scope_occurrences,
    coalesce(execution.occurrence_count, 0) as execution_occurrences,
    case
      when amendment.fiscal_year <> 2026
        then 'blocked_scope_year_not_indexed'
      when coalesce(scope.occurrence_count, 0) = 0
        then 'blocked_scope_not_collected'
      when scope.occurrence_count > 1
        then 'blocked_non_unique_loa_key'
      when coalesce(execution.occurrence_count, 0) = 0
        then 'not_found_in_execution_source'
      when execution.occurrence_count > 1
        then 'blocked_non_unique_execution_key'
      else 'matched_bidirectional_unique'
    end as reconciliation_status,
    execution.execution_code,
    execution.initial_budget_amount,
    execution.current_budget_amount,
    execution.committed_amount,
    execution.liquidated_amount,
    execution.paid_amount,
    execution.source_url as execution_source_url,
    execution.source_artifact_sha256 as execution_source_artifact_sha256,
    execution.evidence_text as execution_evidence_text,
    execution.evidence_sha256 as execution_evidence_sha256,
    execution.source_collected_at as execution_source_collected_at
  from territory.bahia_state_loa_amendments as amendment
  left join scope_counts as scope
    on scope.source_artifact_sha256 = amendment.source_artifact_sha256
   and scope.fiscal_year = amendment.fiscal_year
   and scope.author_external_code = amendment.author_external_code
   and scope.agency_code = amendment.agency_code
   and scope.budget_unit_code = amendment.budget_unit_code
   and scope.action_code = amendment.action_code
  left join execution_counts as execution
    on execution.fiscal_year = amendment.fiscal_year
   and execution.author_external_code = amendment.author_external_code
   and execution.agency_code = amendment.agency_code
   and execution.budget_unit_code = amendment.budget_unit_code
   and execution.action_code = amendment.action_code
)
select
  reconciled.origin_extraction_result_id,
  reconciled.origin_extraction_job_id,
  reconciled.origin_raw_artifact_id,
  reconciled.fiscal_year,
  reconciled.amendment_number,
  reconciled.author_external_code,
  reconciled.author_key,
  reconciled.author_name,
  reconciled.authorized_amount,
  reconciled.official_description,
  reconciled.annex_code,
  reconciled.budget_unit_code,
  reconciled.agency_code,
  reconciled.action_code,
  reconciled.page_number,
  reconciled.evidence_text as loa_evidence_text,
  reconciled.source_url as loa_source_url,
  reconciled.source_artifact_sha256 as loa_source_artifact_sha256,
  reconciled.evidence_sha256 as loa_evidence_sha256,
  reconciled.loa_scope_occurrences,
  reconciled.execution_occurrences,
  reconciled.reconciliation_status,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_code end as execution_code,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.initial_budget_amount end as initial_budget_amount,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.current_budget_amount end as current_budget_amount,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.committed_amount end as committed_amount,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.liquidated_amount end as liquidated_amount,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.paid_amount end as paid_amount,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_source_url end as execution_source_url,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_source_artifact_sha256
    end as execution_source_artifact_sha256,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_evidence_text end as execution_evidence_text,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_evidence_sha256 end as execution_evidence_sha256,
  case when reconciled.reconciliation_status = 'matched_bidirectional_unique'
    then reconciled.execution_source_collected_at
    end as execution_source_collected_at,
  'bahia-state-loa-execution-reconciliation/1.0.0'::text
    as methodology_version
from reconciled;

revoke all on territory.bahia_state_loa_execution_reconciliation from public;
revoke all on territory.bahia_state_loa_execution_reconciliation
  from anon, authenticated;

comment on view territory.bahia_state_loa_execution_reconciliation is
  'Diagnostico privado: liga autorizacao territorial da LOA a execucao estadual somente quando a chave e unica nos dois lados.';

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
  'migration:reconcile-bahia-state-loa-execution',
  'reconciliation.private_projection_created',
  'territory.bahia_state_loa_execution_reconciliation',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version',
    'bahia-state-loa-execution-reconciliation/1.0.0',
    'required_scope_occurrences', 1,
    'required_execution_occurrences', 1
  ),
  jsonb_build_object(
    'public_rpc_created', false,
    'blocked_values_are_null', true,
    'scope_years', jsonb_build_array(2026)
  )
);

commit;
