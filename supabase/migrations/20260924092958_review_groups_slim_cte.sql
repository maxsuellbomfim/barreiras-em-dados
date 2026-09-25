begin;

-- A CTE da fila carregava o payload inteiro de cada empenho pendente (6.518)
-- e gravava em disco temporário: 2,7 s com cache quente e 4,7 s com cache
-- frio, perto do limite de 8 s do papel autenticado. Agrupar só precisa do
-- favorecido e da data: 0,2 s medidos. Mesma assinatura e mesmo resultado.
create or replace function api.get_commitment_link_review_groups(
  page_size integer default 50
)
returns table (
  group_key text,
  reason text,
  creditor_name text,
  pending_count integer,
  link_ids uuid[],
  candidates jsonb,
  samples jsonb,
  first_issue_date date,
  last_issue_date date
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200' using errcode = '22023';
  end if;

  return query
  with pending as materialized (
    select
      link.id,
      link.reason,
      record.payload ->> 'field1144629' as creditor_name,
      to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') as issue_date,
      (
        select string_agg(candidate.contract_portal_id, ',' order by candidate.contract_portal_id)
        from finance.commitment_link_candidates as candidate
        where candidate.link_id = link.id
      ) as candidate_ids
    from finance.commitment_contract_links as link
    join raw.raw_records as record
      on record.id = link.commitment_raw_record_id
    where link.state = 'citacao_sem_confirmacao'
      and link.reason in ('favorecido_divergente', 'varios_contratos')
      and link.rule_version = 'commitment-contract-link/1.0.0'
      and coalesce(
        (
          select review.decision
          from editorial.editorial_reviews as review
          where review.target_type = 'finance.commitment_contract_links'
            and review.target_id = link.id
          order by review.reviewed_at desc, review.id desc
          limit 1
        ),
        'pending'
      ) in ('pending', 'changes_requested')
      and not exists (
        select 1
        from raw.raw_records as newer
        where newer.record_type = 'municipal_commitment_webrun'
          and newer.source_record_key = record.source_record_key
          and (newer.collected_at, newer.id) > (record.collected_at, record.id)
      )
  ),
  groups as (
    select
      md5(pending.reason || '|' || pending.creditor_name || '|' || pending.candidate_ids)
        as group_key,
      pending.reason,
      pending.creditor_name,
      pending.candidate_ids,
      count(*)::integer as pending_count,
      array_agg(pending.id order by pending.issue_date desc, pending.id) as link_ids,
      min(pending.issue_date) as first_issue_date,
      max(pending.issue_date) as last_issue_date
    from pending
    where pending.candidate_ids is not null
    group by 1, 2, 3, 4
  ),
  page as (
    select *
    from groups
    order by groups.pending_count desc, groups.group_key
    limit page_size
  )
  select
    grouped.group_key,
    grouped.reason,
    grouped.creditor_name,
    grouped.pending_count,
    grouped.link_ids,
    (
      select jsonb_agg(
        jsonb_build_object(
          'contract_raw_record_id', candidate.contract_raw_record_id,
          'contract_portal_id', candidate.contract_portal_id,
          'contract_number', candidate.contract_number,
          'contractor', candidate.contractor,
          'contract_object', contract.payload ->> 'contratoObjeto',
          'contract_value_text', contract.payload ->> 'valor_contrato',
          'document_url', contract.payload ->> 'url'
        )
        order by candidate.contract_portal_id
      )
      from finance.commitment_link_candidates as candidate
      join raw.raw_records as contract
        on contract.id = candidate.contract_raw_record_id
      where candidate.link_id = grouped.link_ids[1]
    ),
    (
      select jsonb_agg(sample order by sample ->> 'issue_date' desc)
      from (
        select jsonb_build_object(
          'commitment_key', record.payload ->> 'field1144631',
          'commitment_number', record.payload ->> 'field1082410',
          'issue_date', record.payload ->> 'field1082407',
          'public_body', record.payload ->> 'field1082413',
          'amount_text', record.payload ->> 'field1082412',
          'cited_excerpt', link.cited_excerpt
        ) as sample
        from unnest(grouped.link_ids[1:5]) as sample_link(id)
        join finance.commitment_contract_links as link
          on link.id = sample_link.id
        join raw.raw_records as record
          on record.id = link.commitment_raw_record_id
      ) as samples
    ),
    grouped.first_issue_date,
    grouped.last_issue_date
  from page as grouped
  order by grouped.pending_count desc, grouped.group_key;
end;
$function$;

commit;
