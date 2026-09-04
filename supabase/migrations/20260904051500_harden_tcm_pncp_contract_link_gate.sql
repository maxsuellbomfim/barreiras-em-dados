begin;

create index if not exists extraction_results_tcm_ba_contract_candidates_idx
on raw.extraction_results (created_at, id)
where candidate_type = 'tcm_ba_contract_field_candidate'
  and extractor_version = 'tcm-ba-contract-field-candidates/1.1.1'
  and result_payload ->> 'schema_name' =
    'tcm-ba-contract-field-candidate';

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
        when result.result_payload -> 'source_anchors' ?
          'contracted_party_cnpj'
        then nullif(result.result_payload ->> 'contracted_party_cnpj', '')
      end as contracted_party_cnpj,
      case
        when result.result_payload -> 'source_anchors' ? 'signature_date'
          and result.result_payload ->> 'signature_date' ~
            '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then (result.result_payload ->> 'signature_date')::date
      end as signature_date,
      case
        when result.result_payload -> 'source_anchors' ?
          'administrative_process_number'
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
        and possible.has_corroborator
        and (
          possible.cnpj_match
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
      when not grouped.has_corroborator then 'uncorroborated'
      else 'conflicting_evidence'
    end as link_status,
    case
      when grouped.eligible_match_count <> 1 then null
      when grouped.matched_by_cnpj then 'exact_number_cnpj'
      when grouped.matched_by_date then 'exact_number_date'
      when grouped.matched_by_process then 'exact_number_process'
    end as match_basis,
    case
      when grouped.eligible_match_count = 1 then grouped.matched_contract_id
    end as pncp_contract_id,
    case
      when grouped.eligible_match_count = 1 then grouped.matched_external_id
    end as pncp_external_id,
    grouped.eligible_match_count as match_count,
    'tcm-ba-pncp-contract-link/1.1.0'::text as methodology_version
  from grouped
  order by grouped.source_artifact_sha256, grouped.source_segment_ordinal;
$$;

comment on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
is 'Produz candidatos privados de vínculo TCM-BA/PNCP por número oficial e ao menos um corroborador oficial exato. Não usa nomes, objetos, valores ou similaridade e não publica resultados.';

revoke all on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
  from public, anon, authenticated;
grant usage on schema private to collector_worker;
grant execute on function private.get_tcm_ba_pncp_contract_link_candidates(integer)
  to collector_worker;

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
      count(*) filter (where signature_date is null)::integer
        as candidates_without_signature_date,
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
      )::integer as insufficient_key_candidates,
      count(*) filter (where link_status = 'uncorroborated')::integer
        as uncorroborated_candidates
    from links
  ),
  metrics as (
    select
      tcm_totals.*,
      pncp_totals.*,
      overlap.candidates as exact_number_overlap_candidates,
      link_totals.*,
      link_totals.evaluated_candidates = tcm_totals.candidates_total
        as evaluation_reconciled,
      case
        when tcm_totals.earliest_signature_date is null
          or tcm_totals.latest_signature_date is null
          or pncp_totals.earliest_signed_date is null
          or pncp_totals.latest_signed_date is null
        then null
        else
          tcm_totals.earliest_signature_date <= pncp_totals.latest_signed_date
          and pncp_totals.earliest_signed_date <=
            tcm_totals.latest_signature_date
      end as dated_windows_overlap
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
      when metrics.matched_candidates = 0
        and metrics.uncorroborated_candidates > 0
        then 'official_corroborators_missing'
      when metrics.matched_candidates = 0
        and metrics.conflicting_candidates > 0
        then 'official_evidence_conflicts'
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
    'tcm_candidates_without_signature_date',
      metrics.candidates_without_signature_date,
    'tcm_earliest_signature_date', metrics.earliest_signature_date,
    'tcm_latest_signature_date', metrics.latest_signature_date,
    'pncp_current_contracts_total', metrics.current_contracts_total,
    'pncp_distinct_contract_numbers', metrics.distinct_contract_numbers,
    'pncp_earliest_signed_date', metrics.earliest_signed_date,
    'pncp_latest_signed_date', metrics.latest_signed_date,
    'dated_windows_overlap', metrics.dated_windows_overlap,
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
    'uncorroborated_candidates', metrics.uncorroborated_candidates,
    'methodology_version',
      'tcm-ba-pncp-contract-link-coverage/1.2.0'
  )
  from metrics;
$$;

comment on function private.get_tcm_ba_pncp_contract_link_coverage()
is 'Diagnóstico privado e agregado da cobertura TCM-BA/PNCP, com reconciliação integral, janela temporal datada e bloqueio de números não corroborados. Não retorna pessoas, documentos, valores ou conteúdo bruto.';

revoke all on function private.get_tcm_ba_pncp_contract_link_coverage()
  from public, anon, authenticated;
grant usage on schema private to collector_worker;
grant execute on function private.get_tcm_ba_pncp_contract_link_coverage()
  to collector_worker;

commit;
