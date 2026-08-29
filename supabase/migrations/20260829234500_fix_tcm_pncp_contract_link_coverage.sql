begin;

create or replace function private.get_tcm_ba_pncp_contract_link_coverage()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with tcm_source as (
    select
      result.id as source_result_id,
      result.result_payload,
      case
        when result.result_payload ->> 'document_kind' =
          'contract_amendment'
        then 'related_contract_number'
        else 'instrument_number'
      end as link_field
    from raw.extraction_results as result
    where result.candidate_type = 'tcm_ba_contract_field_candidate'
      and result.extractor_version =
        'tcm-ba-contract-field-candidates/1.1.1'
      and result.result_payload ->> 'schema_name' =
        'tcm-ba-contract-field-candidate'
  ),
  tcm as (
    select
      source_result_id,
      case
        when result_payload -> 'source_anchors' ? link_field
        then nullif(
          regexp_replace(
            upper(result_payload ->> link_field),
            '[^A-Z0-9]',
            '',
            'g'
          ),
          ''
        )
      end as contract_number_normalized,
      case
        when result_payload -> 'source_anchors' ? 'signature_date'
          and result_payload ->> 'signature_date' ~
            '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then (result_payload ->> 'signature_date')::date
      end as signature_date
    from tcm_source
  ),
  tcm_totals as (
    select
      count(*)::integer as candidates_total,
      count(*) filter (
        where contract_number_normalized is not null
      )::integer as candidates_with_contract_number,
      count(*) filter (where signature_date is not null)::integer
        as signature_dates_total,
      min(signature_date) as earliest_signature_date,
      max(signature_date) as latest_signature_date
    from tcm
  ),
  pncp as (
    select distinct on (contract.public_body_id, contract.external_id)
      contract.id,
      nullif(
        regexp_replace(
          upper(contract.contract_number),
          '[^A-Z0-9]',
          '',
          'g'
        ),
        ''
      ) as contract_number_normalized,
      contract.signed_date
    from procurement.contracts as contract
    join org.public_bodies as body
      on body.id = contract.public_body_id
    where body.ibge_code = '2903201'
      and contract.external_id is not null
      and contract.contract_number is not null
    order by
      contract.public_body_id,
      contract.external_id,
      contract.version desc,
      contract.created_at desc
  ),
  pncp_totals as (
    select
      count(*)::integer as current_contracts_total,
      count(distinct contract_number_normalized)::integer
        as distinct_contract_numbers,
      min(signed_date) as earliest_signed_date,
      max(signed_date) as latest_signed_date
    from pncp
  ),
  overlap as (
    select count(*)::integer as candidates
    from tcm
    where tcm.contract_number_normalized is not null
      and exists (
        select 1
        from pncp
        where pncp.contract_number_normalized =
          tcm.contract_number_normalized
      )
  ),
  links as (
    select *
    from private.get_tcm_ba_pncp_contract_link_candidates(5000)
  ),
  link_totals as (
    select
      count(*)::integer as evaluated_candidates,
      count(*) filter (where link_status = 'matched')::integer
        as matched_candidates,
      count(*) filter (where link_status = 'ambiguous')::integer
        as ambiguous_candidates,
      count(*) filter (
        where link_status = 'conflicting_evidence'
      )::integer as conflicting_candidates,
      count(*) filter (where link_status = 'not_found')::integer
        as not_found_candidates,
      count(*) filter (
        where link_status = 'insufficient_key'
      )::integer as insufficient_key_candidates
    from links
  ),
  metrics as (
    select
      tcm_totals.*,
      pncp_totals.*,
      overlap.candidates as exact_number_overlap_candidates,
      link_totals.*,
      link_totals.evaluated_candidates = tcm_totals.candidates_total
        as evaluation_reconciled
    from tcm_totals
    cross join pncp_totals
    cross join overlap
    cross join link_totals
  )
  select jsonb_build_object(
    'operational_state',
    case
      when not metrics.evaluation_reconciled then 'evaluation_incomplete'
      when metrics.candidates_total = 0 then 'tcm_candidates_empty'
      when metrics.candidates_with_contract_number = 0
        then 'tcm_contract_keys_missing'
      when metrics.current_contracts_total = 0 then 'pncp_contracts_empty'
      when metrics.exact_number_overlap_candidates = 0
        then 'no_exact_number_overlap'
      else 'ready_for_review'
    end,
    'publication_gate',
    case
      when metrics.evaluation_reconciled
        and metrics.matched_candidates > 0
      then 'REVIEW_REQUIRED'
      else 'BLOCK'
    end,
    'tcm_candidates_total', metrics.candidates_total,
    'tcm_candidates_with_contract_number',
      metrics.candidates_with_contract_number,
    'tcm_signature_dates_total', metrics.signature_dates_total,
    'tcm_earliest_signature_date', metrics.earliest_signature_date,
    'tcm_latest_signature_date', metrics.latest_signature_date,
    'pncp_current_contracts_total', metrics.current_contracts_total,
    'pncp_distinct_contract_numbers', metrics.distinct_contract_numbers,
    'pncp_earliest_signed_date', metrics.earliest_signed_date,
    'pncp_latest_signed_date', metrics.latest_signed_date,
    'exact_number_overlap_candidates',
      metrics.exact_number_overlap_candidates,
    'evaluated_candidates', metrics.evaluated_candidates,
    'evaluation_reconciled', metrics.evaluation_reconciled,
    'evaluation_truncated',
      metrics.evaluated_candidates < metrics.candidates_total,
    'matched_candidates', metrics.matched_candidates,
    'ambiguous_candidates', metrics.ambiguous_candidates,
    'conflicting_candidates', metrics.conflicting_candidates,
    'not_found_candidates', metrics.not_found_candidates,
    'insufficient_key_candidates', metrics.insufficient_key_candidates,
    'methodology_version',
      'tcm-ba-pncp-contract-link-coverage/1.1.0'
  )
  from metrics;
$$;

comment on function private.get_tcm_ba_pncp_contract_link_coverage()
is 'Diagnóstico privado e agregado da cobertura de chaves oficiais entre documentos contratuais TCM-BA e contratos PNCP de Barreiras, com reconciliação do universo avaliado e faixas temporais. Não retorna pessoas, documentos, valores ou conteúdo bruto.';

revoke all on function private.get_tcm_ba_pncp_contract_link_coverage()
  from public, anon, authenticated;
grant usage on schema private to collector_worker;
grant execute on function private.get_tcm_ba_pncp_contract_link_coverage()
  to collector_worker;

commit;
