begin;

create or replace function private.get_tcm_ba_pncp_contract_link_candidates(
  p_limit integer default 5000
)
returns table (
  source_result_id uuid,
  source_artifact_sha256 text,
  source_segment_ordinal integer,
  document_kind text,
  link_status text,
  match_basis text,
  pncp_contract_id uuid,
  pncp_external_id text,
  match_count integer,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  with tcm as (
    select
      result.id as source_result_id,
      result.result_payload ->> 'source_artifact_sha256'
        as source_artifact_sha256,
      (result.result_payload ->> 'source_segment_ordinal')::integer
        as source_segment_ordinal,
      result.result_payload ->> 'document_kind' as document_kind,
      case
        when result.result_payload ->> 'document_kind' = 'contract_amendment'
        then result.result_payload ->> 'related_contract_number'
        else result.result_payload ->> 'instrument_number'
      end as link_number,
      case
        when result.result_payload ->> 'document_kind' = 'contract_amendment'
        then 'related_contract_number'
        else 'instrument_number'
      end as link_field,
      case
        when result.result_payload -> 'source_anchors'
          ? 'contracted_party_cnpj'
        then nullif(result.result_payload ->> 'contracted_party_cnpj', '')
      end as contracted_party_cnpj,
      case
        when result.result_payload -> 'source_anchors' ? 'signature_date'
          and result.result_payload ->> 'signature_date'
            ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then (result.result_payload ->> 'signature_date')::date
      end as signature_date,
      case
        when result.result_payload -> 'source_anchors'
          ? 'administrative_process_number'
        then nullif(
          regexp_replace(
            upper(result.result_payload ->> 'administrative_process_number'),
            '[^A-Z0-9]',
            '',
            'g'
          ),
          ''
        )
      end as process_number_normalized,
      result.result_payload -> 'source_anchors' as source_anchors
    from raw.extraction_results as result
    where result.candidate_type = 'tcm_ba_contract_field_candidate'
      and result.extractor_version =
        'tcm-ba-contract-field-candidates/1.1.1'
      and result.result_payload ->> 'schema_name' =
        'tcm-ba-contract-field-candidate'
    order by result.created_at, result.id
    limit least(greatest(coalesce(p_limit, 5000), 1), 5000)
  ),
  tcm_normalized as (
    select
      tcm.*,
      case
        when tcm.source_anchors ? tcm.link_field
        then nullif(
          regexp_replace(upper(tcm.link_number), '[^A-Z0-9]', '', 'g'),
          ''
        )
      end as contract_number_normalized
    from tcm
  ),
  pncp as (
    select distinct on (contract.public_body_id, contract.external_id)
      contract.id,
      contract.external_id,
      nullif(
        regexp_replace(upper(contract.contract_number), '[^A-Z0-9]', '', 'g'),
        ''
      ) as contract_number_normalized,
      contract.signed_date,
      supplier.public_registration_number as supplier_cnpj,
      nullif(
        regexp_replace(upper(procurement.process_number), '[^A-Z0-9]', '', 'g'),
        ''
      ) as process_number_normalized
    from procurement.contracts as contract
    join org.public_bodies as body
      on body.id = contract.public_body_id
    left join procurement.suppliers as supplier
      on supplier.id = contract.supplier_id
    left join procurement.procurements as procurement
      on procurement.id = contract.procurement_id
    where body.ibge_code = '2903201'
      and contract.external_id is not null
      and contract.contract_number is not null
    order by
      contract.public_body_id,
      contract.external_id,
      contract.version desc,
      contract.created_at desc
  ),
  possible as (
    select
      tcm.*,
      pncp.id as candidate_contract_id,
      pncp.external_id as candidate_external_id,
      pncp.id is not null as number_match,
      tcm.contracted_party_cnpj is not null
        or tcm.signature_date is not null
        or tcm.process_number_normalized is not null
        as has_corroborator,
      tcm.contracted_party_cnpj is not null
        and pncp.supplier_cnpj = tcm.contracted_party_cnpj
        as cnpj_match,
      tcm.signature_date is not null
        and pncp.signed_date = tcm.signature_date
        as date_match,
      tcm.process_number_normalized is not null
        and pncp.process_number_normalized = tcm.process_number_normalized
        as process_match
    from tcm_normalized as tcm
    left join pncp
      on pncp.contract_number_normalized = tcm.contract_number_normalized
  ),
  evaluated as (
    select
      possible.*,
      possible.number_match
        and (
          not possible.has_corroborator
          or possible.cnpj_match
          or possible.date_match
          or possible.process_match
        ) as eligible_match
    from possible
  ),
  grouped as (
    select
      evaluated.source_result_id,
      min(evaluated.source_artifact_sha256) as source_artifact_sha256,
      min(evaluated.source_segment_ordinal) as source_segment_ordinal,
      min(evaluated.document_kind) as document_kind,
      min(evaluated.contract_number_normalized)
        as contract_number_normalized,
      bool_or(evaluated.has_corroborator) as has_corroborator,
      count(distinct evaluated.candidate_contract_id)
        filter (where evaluated.number_match)::integer as number_match_count,
      count(distinct evaluated.candidate_contract_id)
        filter (where evaluated.eligible_match)::integer as eligible_match_count,
      (
        array_agg(distinct evaluated.candidate_contract_id)
          filter (where evaluated.eligible_match)
      )[1] as matched_contract_id,
      min(evaluated.candidate_external_id)
        filter (where evaluated.eligible_match) as matched_external_id,
      bool_or(evaluated.cnpj_match)
        filter (where evaluated.eligible_match) as matched_by_cnpj,
      bool_or(evaluated.date_match)
        filter (where evaluated.eligible_match) as matched_by_date,
      bool_or(evaluated.process_match)
        filter (where evaluated.eligible_match) as matched_by_process
    from evaluated
    group by evaluated.source_result_id
  )
  select
    grouped.source_result_id,
    grouped.source_artifact_sha256,
    grouped.source_segment_ordinal,
    grouped.document_kind,
    case
      when grouped.contract_number_normalized is null then 'insufficient_key'
      when grouped.eligible_match_count = 1 then 'matched'
      when grouped.eligible_match_count > 1 then 'ambiguous'
      when grouped.number_match_count = 0 then 'not_found'
      when grouped.has_corroborator then 'conflicting_evidence'
      else 'not_found'
    end as link_status,
    case
      when grouped.eligible_match_count <> 1 then null
      when grouped.matched_by_cnpj then 'exact_number_cnpj'
      when grouped.matched_by_date then 'exact_number_date'
      when grouped.matched_by_process then 'exact_number_process'
      else 'exact_unique_number'
    end as match_basis,
    case
      when grouped.eligible_match_count = 1 then grouped.matched_contract_id
    end as pncp_contract_id,
    case
      when grouped.eligible_match_count = 1 then grouped.matched_external_id
    end as pncp_external_id,
    grouped.eligible_match_count as match_count,
    'tcm-ba-pncp-contract-link/1.0.0'::text as methodology_version
  from grouped
  order by grouped.source_artifact_sha256, grouped.source_segment_ordinal;
$$;

comment on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
is 'Produz candidatos privados de vínculo TCM-BA/PNCP apenas por chaves oficiais exatas. Não usa nomes, objetos, valores ou similaridade e não publica resultados.';

revoke all on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
  from public, anon, authenticated;
grant usage on schema private to collector_worker;
grant execute on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
  to collector_worker;

commit;
