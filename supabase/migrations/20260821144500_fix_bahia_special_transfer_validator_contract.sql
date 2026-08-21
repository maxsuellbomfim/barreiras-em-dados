-- Corrige o contrato entre o normalizador de transferencias especiais e a
-- projecao publica. A migration anterior aceitava um identificador de
-- validador que nunca foi emitido pelo worker em producao.

create or replace view territory.latest_bahia_special_transfer_payment_candidates
with (security_barrier = true)
as
select distinct on (typed.payment_id)
  typed.extraction_result_id,
  typed.raw_artifact_id,
  typed.fiscal_year,
  typed.amendment_number,
  typed.amendment_year,
  typed.source_author_name,
  typed.source_author_code,
  typed.official_amendment_code,
  typed.agency_name,
  typed.agency_code,
  typed.budget_unit_name,
  typed.budget_unit_code,
  typed.action_name,
  typed.expense_code,
  typed.execution_code,
  typed.payment_id,
  typed.payment_number,
  typed.payment_date,
  typed.payment_amount,
  typed.gcv_amount,
  typed.payment_status,
  typed.object_text,
  typed.payment_url,
  typed.territorial_scope,
  typed.evidence_text,
  typed.evidence_sha256,
  typed.source_url,
  typed.source_artifact_sha256,
  typed.source_collected_at,
  typed.result_created_at
from (
  select
    result.id as extraction_result_id,
    job.raw_artifact_id,
    case when result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
      then (result.result_payload ->> 'fiscal_year')::smallint
    end as fiscal_year,
    btrim(result.result_payload ->> 'amendment_number') as amendment_number,
    case when result.result_payload ->> 'amendment_year' ~ '^[0-9]{4}$'
      then (result.result_payload ->> 'amendment_year')::smallint
    end as amendment_year,
    btrim(result.result_payload ->> 'author_name') as source_author_name,
    case
      when btrim(result.result_payload ->> 'amendment_number') ~ '^[0-9]{8}$'
      then left(btrim(result.result_payload ->> 'amendment_number'), 4)
    end as source_author_code,
    case
      when result.result_payload ->> 'amendment_year' ~ '^[0-9]{4}$'
        and btrim(result.result_payload ->> 'amendment_number') ~ '^[0-9]{8}$'
      then (result.result_payload ->> 'amendment_year')
        || btrim(result.result_payload ->> 'amendment_number')
    end as official_amendment_code,
    btrim(result.result_payload ->> 'agency_name') as agency_name,
    btrim(result.result_payload ->> 'agency_code') as agency_code,
    btrim(result.result_payload ->> 'budget_unit_name') as budget_unit_name,
    btrim(result.result_payload ->> 'budget_unit_code') as budget_unit_code,
    btrim(result.result_payload ->> 'action_name') as action_name,
    btrim(result.result_payload ->> 'expense_code') as expense_code,
    btrim(result.result_payload ->> 'execution_code') as execution_code,
    btrim(result.result_payload ->> 'payment_id') as payment_id,
    btrim(result.result_payload ->> 'payment_number') as payment_number,
    case when result.result_payload ->> 'payment_date'
      ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (result.result_payload ->> 'payment_date')::date
    end as payment_date,
    case when result.result_payload ->> 'payment_amount'
      ~ '^-?[0-9]+[.][0-9]{2}$'
      then (result.result_payload ->> 'payment_amount')::numeric(20,2)
    end as payment_amount,
    case
      when result.result_payload ->> 'gcv_amount' is null then null
      when result.result_payload ->> 'gcv_amount' ~ '^-?[0-9]+[.][0-9]{2}$'
      then (result.result_payload ->> 'gcv_amount')::numeric(20,2)
    end as gcv_amount,
    btrim(result.result_payload ->> 'payment_status') as payment_status,
    btrim(result.result_payload ->> 'object_text') as object_text,
    btrim(result.result_payload ->> 'payment_url') as payment_url,
    btrim(result.result_payload ->> 'territorial_scope') as territorial_scope,
    btrim(result.result_payload ->> 'evidence_text') as evidence_text,
    btrim(result.result_payload ->> 'evidence_sha256') as evidence_sha256,
    btrim(result.result_payload ->> 'source_url') as source_url,
    btrim(result.result_payload ->> 'source_artifact_sha256')
      as source_artifact_sha256,
    case when result.result_payload ->> 'source_collected_at' is not null
      then (result.result_payload ->> 'source_collected_at')::timestamptz
    end as source_collected_at,
    result.created_at as result_created_at
  from raw.extraction_results as result
  join raw.extraction_jobs as job on job.id = result.extraction_job_id
  where result.candidate_type =
      'bahia_special_transfer_payment_candidate'
    and result.extractor_version =
      'bahia-special-transfer-payment/1.0.0'
    and result.validator_version =
      'bahia-special-transfer-territorial-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and job.status = 'succeeded'
    and result.result_payload ->> 'schema_name' =
      'bahia-special-transfer-payment-candidate'
    and result.result_payload ->> 'schema_version' = '1.0.0'
) as typed
where typed.fiscal_year between 2000 and 2100
  and typed.amendment_year between 2000 and 2100
  and typed.amendment_number ~ '^[0-9]{8}$'
  and typed.payment_id ~ '^[0-9]{18,19}$'
  and typed.payment_date is not null
  and typed.payment_amount is not null
  and typed.source_author_name is not null
  and typed.source_author_name <> ''
  and typed.payment_status in ('Sim', 'Não', 'Em Processamento')
  and typed.object_text <> ''
  and typed.payment_url ~ '^https://www[.]transparencia[.]ba[.]gov[.]br/'
  and typed.territorial_scope = 'payment_object_literal_barreiras'
  and typed.evidence_sha256 ~ '^[0-9a-f]{64}$'
  and typed.source_url ~ '^https://'
  and typed.source_artifact_sha256 ~ '^[0-9a-f]{64}$'
  and typed.source_collected_at is not null
order by
  typed.payment_id,
  typed.source_collected_at desc,
  typed.result_created_at desc,
  typed.extraction_result_id desc;

comment on view territory.latest_bahia_special_transfer_payment_candidates is
  'Resultados territoriais validados pelo identificador exato emitido pelo worker; identificadores do credor permanecem privados.';

revoke all on territory.latest_bahia_special_transfer_payment_candidates
  from public, anon, authenticated;
