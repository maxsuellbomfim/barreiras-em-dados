begin;

-- Atualiza a função-base criada pelo vínculo de execução e preserva o wrapper
-- que acrescenta metadados de documentos oficiais filhos.
create or replace function api.get_pncp_execution_summary_base(control_number_filter text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $function$
  with procurement_row as (
    select p.id, p.origin_raw_record_id
    from procurement.procurements as p
    where p.external_id = nullif(trim(control_number_filter), '')
    order by p.version desc, p.created_at desc, p.id desc
    limit 1
  ),
  current_contracts as (
    select
      c.id,
      c.origin_raw_record_id,
      c.external_id,
      c.contract_number,
      c.initial_amount,
      c.current_amount,
      c.signed_date,
      c.effective_from,
      c.effective_until,
      supplier.legal_name as supplier_name,
      supplier.public_registration_number as supplier_registration_number,
      artifact.source_url,
      artifact.retrieved_at
    from procurement.contracts as c
    join procurement_row as p on p.id = c.procurement_id
    left join procurement.suppliers as supplier on supplier.id = c.supplier_id
    left join raw.raw_records as origin on origin.id = c.origin_raw_record_id
    left join raw.raw_artifacts as artifact on artifact.id = origin.raw_artifact_id
    where not exists (
      select 1
      from procurement.contracts as newer
      where newer.supersedes_id = c.id
    )
  ),
  contract_summary as (
    select coalesce(
      jsonb_agg(
        jsonb_build_object(
          'external_id', contract.external_id,
          'contract_number', contract.contract_number,
          'supplier_name', contract.supplier_name,
          'supplier_registration_number', contract.supplier_registration_number,
          'initial_amount', contract.initial_amount,
          'current_amount', contract.current_amount,
          'signed_date', contract.signed_date,
          'effective_from', contract.effective_from,
          'effective_until', contract.effective_until,
          'source_url', contract.source_url,
          'retrieved_at', contract.retrieved_at
        )
        order by contract.signed_date desc nulls last, contract.external_id
      ),
      '[]'::jsonb
    ) as entries
    from current_contracts as contract
  ),
  current_commitments as (
    select c.id, c.origin_raw_record_id, c.amount, c.cancelled_amount
    from finance.commitments as c
    join procurement_row as p
      on c.procurement_id = p.id
      or c.contract_id in (select id from current_contracts)
    where not exists (
      select 1
      from finance.commitments as newer
      where newer.supersedes_id = c.id
    )
  ),
  current_liquidations as (
    select l.id, l.origin_raw_record_id, l.commitment_id, l.amount, l.cancelled_amount
    from finance.liquidations as l
    where l.commitment_id in (select id from current_commitments)
      and not exists (
        select 1
        from finance.liquidations as newer
        where newer.supersedes_id = l.id
      )
  ),
  current_payments as (
    select p.id, p.origin_raw_record_id, p.amount, p.reversed_amount
    from finance.payments as p
    where (
      p.commitment_id in (select id from current_commitments)
      or p.liquidation_id in (select id from current_liquidations)
    )
      and not exists (
        select 1
        from finance.payments as newer
        where newer.supersedes_id = p.id
      )
  ),
  evidence_rows as (
    select 'contratacao'::text as entity_type, p.origin_raw_record_id
    from procurement_row as p
    where p.origin_raw_record_id is not null
    union all
    select 'contrato', c.origin_raw_record_id
    from current_contracts as c
    where c.origin_raw_record_id is not null
    union all
    select 'empenho', c.origin_raw_record_id
    from current_commitments as c
    where c.origin_raw_record_id is not null
    union all
    select 'liquidacao', l.origin_raw_record_id
    from current_liquidations as l
    where l.origin_raw_record_id is not null
    union all
    select 'pagamento', p.origin_raw_record_id
    from current_payments as p
    where p.origin_raw_record_id is not null
  ),
  evidence_candidates as (
    select distinct on (r.id)
      e.entity_type,
      r.id as raw_record_id,
      r.record_type,
      a.source_url,
      a.sha256,
      a.retrieved_at,
      a.collector_version,
      r.parser_version
    from evidence_rows as e
    join raw.raw_records as r on r.id = e.origin_raw_record_id
    join raw.raw_artifacts as a on a.id = r.raw_artifact_id
    order by r.id, a.retrieved_at desc
  ),
  evidence_summary as (
    select coalesce(
      jsonb_agg(
        jsonb_build_object(
          'entity_type', candidate.entity_type,
          'raw_record_id', candidate.raw_record_id,
          'record_type', candidate.record_type,
          'source_url', candidate.source_url,
          'sha256', candidate.sha256,
          'retrieved_at', candidate.retrieved_at,
          'collector_version', candidate.collector_version,
          'parser_version', candidate.parser_version
        )
        order by candidate.retrieved_at desc, candidate.entity_type
      ),
      '[]'::jsonb
    ) as entries
    from (
      select *
      from evidence_candidates
      order by retrieved_at desc, entity_type
      limit 20
    ) as candidate
  ),
  totals as (
    select
      (select count(*)::integer from current_contracts) as contracts_count,
      (select count(*)::integer from current_commitments) as commitments_count,
      (select count(*)::integer from current_liquidations) as liquidations_count,
      (select count(*)::integer from current_payments) as payments_count,
      coalesce((select sum(current_amount) from current_contracts), 0)::numeric as contract_current_amount,
      coalesce((select sum(amount - cancelled_amount) from current_commitments), 0)::numeric as committed_amount,
      coalesce((select sum(amount - cancelled_amount) from current_liquidations), 0)::numeric as liquidated_amount,
      coalesce((select sum(amount - reversed_amount) from current_payments), 0)::numeric as paid_amount
  )
  select jsonb_build_object(
    'state', case
      when not exists (select 1 from procurement_row) then 'not_normalized'
      when totals.contracts_count + totals.commitments_count + totals.liquidations_count + totals.payments_count = 0
        then 'no_linked_execution'
      else 'linked'
    end,
    'methodology_version', 'pncp-execution-links/1.3.0',
    'contracts_count', totals.contracts_count,
    'commitments_count', totals.commitments_count,
    'liquidations_count', totals.liquidations_count,
    'payments_count', totals.payments_count,
    'contract_current_amount', totals.contract_current_amount,
    'committed_amount', totals.committed_amount,
    'liquidated_amount', totals.liquidated_amount,
    'paid_amount', totals.paid_amount,
    'contracts', contract_summary.entries,
    'evidence_count', jsonb_array_length(evidence_summary.entries),
    'evidence', evidence_summary.entries
  )
  from totals
  cross join evidence_summary
  cross join contract_summary;
$function$;

-- Mantém a proteção do wrapper: o Storage segue privado e os metadados de
-- documentos filhos continuam sendo anexados à evidência pública.
create or replace function api.get_pncp_execution_summary(control_number_filter text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $function$
  with base as (
    select api.get_pncp_execution_summary_base(control_number_filter) as summary
  ),
  enriched as (
    select coalesce(
      jsonb_agg(
        item.item || jsonb_build_object(
          'document_source_url', child.source_url,
          'document_sha256', child.sha256,
          'document_retrieved_at', child.retrieved_at,
          'document_preserved', child.id is not null
        )
        order by item.ordinality
      ),
      '[]'::jsonb
    ) as entries
    from base
    cross join lateral jsonb_array_elements(
      coalesce(base.summary -> 'evidence', '[]'::jsonb)
    ) with ordinality as item(item, ordinality)
    left join raw.raw_records as record
      on record.id = nullif(item.item ->> 'raw_record_id', '')::uuid
    left join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    left join lateral (
      select document.id, document.source_url, document.sha256, document.retrieved_at
      from raw.raw_artifacts as document
      where document.parent_artifact_id = artifact.id
        and document.artifact_kind = 'document'
        and document.source_url ~ '^https://'
      order by document.created_at desc, document.id desc
      limit 1
    ) as child on true
  )
  select base.summary || jsonb_build_object(
    'methodology_version', 'pncp-execution-links/1.3.0',
    'evidence', enriched.entries
  )
  from base
  cross join enriched;
$function$;

revoke all on function api.get_pncp_execution_summary_base(text)
  from public, anon, authenticated;
revoke all on function api.get_pncp_execution_summary(text)
  from public, anon, authenticated;

comment on function api.get_pncp_execution_summary_base(text) is
  'Resumo determinístico de execução PNCP com detalhes de contratos normalizados.';
comment on function api.get_pncp_execution_summary(text) is
  'Resumo PNCP com detalhes de contratos e documento oficial filho quando preservado.';

commit;
