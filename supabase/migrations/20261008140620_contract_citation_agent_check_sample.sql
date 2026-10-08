begin;

-- ADR 0096 (emenda de 08/10/2026): a amostra informa se a decisão vigente é
-- humana ou automática por agente.

drop function api.get_contract_citation_review_sample();
create function api.get_contract_citation_review_sample()
returns table (
  sample_order integer,
  sample_reason text,
  category text,
  public_body text,
  creditor_name text,
  creditor_is_entity boolean,
  cited_number text,
  cited_excerpt text,
  commitments integer,
  paid_amount text,
  first_issue_date date,
  last_issue_date date,
  latest_commitment_key text,
  list_read_on date,
  pncp_url text,
  portal_contracts_url text,
  current_decision text,
  current_reviewed_at timestamptz,
  current_review_kind text,
  methodology_version text
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

  return query
  with groups as (
    select
      comparison.category,
      comparison.public_body,
      comparison.creditor_name,
      bool_and(comparison.creditor_is_entity) as creditor_is_entity,
      comparison.cited_number,
      (array_agg(comparison.cited_excerpt
        order by comparison.issue_date desc, comparison.commitment_key desc))[1] as excerpt,
      count(*)::integer as commitments,
      sum(comparison.paid_amount) as paid,
      min(comparison.issue_date) as first_date,
      max(comparison.issue_date) as last_date,
      (array_agg(comparison.commitment_key
        order by comparison.issue_date desc, comparison.commitment_key desc))[1] as latest_key,
      max(comparison.list_read_on) as read_on,
      max(comparison.pncp_url) as pncp_url
    from finance.contract_citation_comparison_v1(null) as comparison
    group by 1, 2, 3, 5
  ),
  ranked as (
    select
      groups.*,
      -- Semente fixa: a mesma amostra sai para qualquer revisor.
      md5(groups.public_body || '|' || groups.creditor_name || '|' || groups.cited_number
        || '|contract-citation-comparison/1.0.0') as seed_order,
      groups.cited_number in ('338/2020', '308/2023') as measured_example
    from groups
  ),
  chosen as (
    select ranked.*, 'exemplo da medição'::text as reason, 0 as tier
    from ranked
    where ranked.measured_example
    union all
    select picked.*, 'sorteio de semente fixa'::text, 1
    from (
      select ranked.*
      from ranked
      where not ranked.measured_example
      order by ranked.seed_order
      limit 20
    ) as picked
  ),
  review as (
    select * from finance.contract_citation_review_v1()
  )
  select
    (row_number() over (order by chosen.tier, chosen.seed_order))::integer,
    chosen.reason,
    chosen.category,
    chosen.public_body,
    chosen.creditor_name,
    chosen.creditor_is_entity,
    chosen.cited_number,
    chosen.excerpt,
    chosen.commitments,
    to_char(chosen.paid, 'FM999999999990.00'),
    chosen.first_date,
    chosen.last_date,
    chosen.latest_key,
    chosen.read_on,
    chosen.pncp_url,
    'https://portaldatransparencia.barreiras.ba.gov.br/contratos'::text,
    (select review.decision from review),
    (select review.reviewed_at from review),
    (select review.review_kind from review),
    'contract-citation-comparison/1.0.0'::text
  from chosen
  order by chosen.tier, chosen.seed_order;
end;
$function$;

revoke all on function api.get_contract_citation_review_sample() from public, anon;
grant execute on function api.get_contract_citation_review_sample() to authenticated;

comment on function api.get_contract_citation_review_sample() is
  'Amostra de conferência do ADR 0096 (só revisor ativo): exemplos da medição e 20 grupos por semente fixa, com nome do credor para conferir no portal.';

commit;
