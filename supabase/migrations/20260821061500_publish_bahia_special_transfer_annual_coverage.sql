-- Publica somente contagens anuais sanitizadas do retrato integral de
-- Transferencias Especiais. Nenhum campo de credor integra esta projecao.

create view territory.latest_bahia_special_transfer_annual_coverage
with (security_barrier = true)
as
with latest_result as (
  select
    result.id as extraction_result_id,
    result.result_payload,
    artifact.retrieved_at as source_collected_at,
    artifact.sha256 as artifact_sha256
  from raw.extraction_results as result
  join raw.extraction_jobs as job on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact on artifact.id = job.raw_artifact_id
  where result.candidate_type =
      'bahia_special_transfer_annual_coverage'
    and result.extractor_version =
      'bahia-special-transfer-payment/1.0.0'
    and result.validator_version =
      'bahia-special-transfer-territorial-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and job.status = 'succeeded'
  order by artifact.retrieved_at desc, result.created_at desc, result.id desc
  limit 1
), valid_snapshot as (
  select latest.*
  from latest_result as latest
  where latest.result_payload ->> 'schema_name' =
      'bahia-special-transfer-annual-coverage'
    and latest.result_payload ->> 'schema_version' = '1.0.0'
    and latest.result_payload ->> 'parser_version' =
      'bahia-special-transfer-payment/1.0.0'
    and latest.result_payload ->> 'territorial_scope' =
      'payment_object_literal_barreiras'
    and latest.result_payload ->> 'source_url' ~ '^https://'
    and latest.result_payload ->> 'source_artifact_sha256' ~
      '^[0-9a-f]{64}$'
    and latest.result_payload ->> 'source_artifact_sha256' =
      latest.artifact_sha256
    and latest.result_payload ->> 'coverage_start_year' = '2021'
    and substring(
      latest.result_payload ->> 'coverage_end_year'
      from '^[0-9]{4}$'
    ) is not null
    and substring(
      latest.result_payload ->> 'coverage_end_year'
      from '^[0-9]{4}$'
    )::integer between 2021 and 2100
    and jsonb_typeof(latest.result_payload -> 'years') = 'array'
    and not exists (
      select 1
      from jsonb_array_elements(latest.result_payload -> 'years') as item
      where jsonb_typeof(item) <> 'object'
        or substring(item ->> 'fiscal_year' from '^[0-9]{4}$') is null
        or substring(
          item ->> 'source_payment_count' from '^[1-9][0-9]{0,8}$'
        ) is null
        or substring(
          item ->> 'territorial_payment_count' from '^[0-9]{1,9}$'
        ) is null
        or substring(
          item ->> 'fiscal_year' from '^[0-9]{4}$'
        )::integer not between 2021 and 2100
        or substring(
          item ->> 'fiscal_year' from '^[0-9]{4}$'
        )::integer > substring(
          latest.result_payload ->> 'coverage_end_year'
          from '^[0-9]{4}$'
        )::integer
        or substring(
          item ->> 'territorial_payment_count' from '^[0-9]{1,9}$'
        )::integer > substring(
          item ->> 'source_payment_count' from '^[1-9][0-9]{0,8}$'
        )::integer
    )
    and (
      select count(*) = count(distinct item ->> 'fiscal_year')
      from jsonb_array_elements(latest.result_payload -> 'years') as item
    )
)
select
  substring(year_item ->> 'fiscal_year' from '^[0-9]{4}$')::smallint
    as fiscal_year,
  substring(
    year_item ->> 'source_payment_count' from '^[1-9][0-9]{0,8}$'
  )::integer
    as source_payment_count,
  substring(
    year_item ->> 'territorial_payment_count' from '^[0-9]{1,9}$'
  )::integer
    as territorial_payment_count,
  case
    when substring(
      year_item ->> 'territorial_payment_count' from '^[0-9]{1,9}$'
    )::integer > 0
      then 'territorial_records_observed'
    else 'collected_no_territorial_record'
  end as territorial_status,
  'source_snapshot_processed'::text as source_snapshot_status,
  valid.result_payload ->> 'territorial_scope' as territorial_scope,
  valid.result_payload ->> 'source_url' as source_url,
  valid.artifact_sha256 as source_artifact_sha256,
  valid.source_collected_at,
  valid.extraction_result_id
from valid_snapshot as valid
cross join lateral jsonb_array_elements(
  valid.result_payload -> 'years'
) as year_item;

comment on view territory.latest_bahia_special_transfer_annual_coverage is
  'Contagens anuais do ultimo retrato estadual processado; nao sao valores financeiros nem prova de recebimento municipal.';

revoke all on territory.latest_bahia_special_transfer_annual_coverage
  from public, anon, authenticated;

create function api.get_public_bahia_special_transfer_annual_coverage()
returns table (
  fiscal_year smallint,
  source_payment_count integer,
  territorial_payment_count integer,
  territorial_status text,
  source_snapshot_status text,
  territorial_scope text,
  source_url text,
  source_artifact_sha256 text,
  source_collected_at timestamptz,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    coverage.fiscal_year,
    coverage.source_payment_count,
    coverage.territorial_payment_count,
    coverage.territorial_status,
    coverage.source_snapshot_status,
    coverage.territorial_scope,
    coverage.source_url,
    coverage.source_artifact_sha256,
    coverage.source_collected_at,
    'bahia-special-transfer-annual-coverage/1.0.0'::text
  from territory.latest_bahia_special_transfer_annual_coverage as coverage
  order by coverage.fiscal_year desc;
$$;

revoke all on function
  api.get_public_bahia_special_transfer_annual_coverage()
  from public;
grant execute on function
  api.get_public_bahia_special_transfer_annual_coverage()
  to anon, authenticated;

comment on function
  api.get_public_bahia_special_transfer_annual_coverage() is
  'Publica contagens por exercicio do retrato estadual, sem dados de credor e sem fabricar valor financeiro.';

update source.source_endpoints as endpoint
set config = endpoint.config || jsonb_build_object(
  'annual_coverage_projection',
    'api.get_public_bahia_special_transfer_annual_coverage',
  'annual_coverage_methodology',
    'bahia-special-transfer-annual-coverage/1.0.0',
  'annual_coverage_is_financial_amount', false,
  'annual_coverage_contains_creditor_data', false
)
from source.data_sources as source
where endpoint.data_source_id = source.id
  and source.slug = 'bahia-open-data'
  and endpoint.slug = 'state-special-transfers';

do $$
begin
  perform pg_notify('pgrst', 'reload schema');
end
$$;
