-- Evidencias de origem para cada vinculo financeiro. A lista e limitada para
-- manter a resposta publica pequena; os registros brutos continuam completos.

create or replace function api.get_pncp_execution_summary(control_number_filter text)
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
    select c.id, c.origin_raw_record_id, c.current_amount
    from procurement.contracts as c
    join procurement_row as p on p.id = c.procurement_id
    where not exists (
      select 1 from procurement.contracts as newer where newer.supersedes_id = c.id
    )
  ),
  current_commitments as (
    select c.id, c.origin_raw_record_id, c.amount, c.cancelled_amount
    from finance.commitments as c
    join procurement_row as p
      on c.procurement_id = p.id
      or c.contract_id in (select id from current_contracts)
    where not exists (
      select 1 from finance.commitments as newer where newer.supersedes_id = c.id
    )
  ),
  current_liquidations as (
    select l.id, l.origin_raw_record_id, l.commitment_id, l.amount, l.cancelled_amount
    from finance.liquidations as l
    where l.commitment_id in (select id from current_commitments)
      and not exists (
        select 1 from finance.liquidations as newer where newer.supersedes_id = l.id
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
        select 1 from finance.payments as newer where newer.supersedes_id = p.id
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
        ) order by candidate.retrieved_at desc, candidate.entity_type
      ),
      '[]'::jsonb
    ) as entries
    from (
      select * from evidence_candidates
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
    'methodology_version', 'pncp-execution-links/1.1.0',
    'contracts_count', totals.contracts_count,
    'commitments_count', totals.commitments_count,
    'liquidations_count', totals.liquidations_count,
    'payments_count', totals.payments_count,
    'contract_current_amount', totals.contract_current_amount,
    'committed_amount', totals.committed_amount,
    'liquidated_amount', totals.liquidated_amount,
    'paid_amount', totals.paid_amount,
    'evidence_count', jsonb_array_length(evidence_summary.entries),
    'evidence', evidence_summary.entries
  )
  from totals cross join evidence_summary;
$function$;

revoke all on function api.get_pncp_execution_summary(text) from public, anon, authenticated;

comment on function api.get_pncp_execution_summary(text) is
  'Resumo de vinculos PNCP com valores deterministas e metadados de evidencia preservados.';
