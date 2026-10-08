begin;

-- ADR 0096 (emenda de 08/10/2026): a função pública diz se a conferência que
-- liberou a publicação foi humana ou automática por agente (review_kind).

drop function api.get_public_contract_citations(integer);
create function api.get_public_contract_citations(p_year integer)
returns table (
  review_state text,
  approved_at timestamptz,
  review_kind text,
  row_kind text,
  category text,
  public_body text,
  creditor_name text,
  cited_number text,
  cited_excerpt text,
  commitments integer,
  payments integer,
  unreadable_payments integer,
  paid_amount text,
  first_issue_date date,
  last_issue_date date,
  list_read_on date,
  latest_commitment_key text,
  pncp_url text,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  latest_decision text;
  latest_reviewed_at timestamptz;
  latest_kind text;
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;

  select review.decision, review.reviewed_at, review.review_kind
  into latest_decision, latest_reviewed_at, latest_kind
  from finance.contract_citation_review_v1() as review;

  if latest_decision is distinct from 'approved' then
    return query select
      'awaiting_review'::text, null::timestamptz, null::text, 'status'::text, null::text,
      null::text, null::text, null::text, null::text, null::integer, null::integer,
      null::integer, null::text, null::date, null::date, null::date, null::text, null::text,
      'https://portaldatransparencia.barreiras.ba.gov.br/contratos'::text,
      'contract-citation-comparison/1.0.0'::text;
    return;
  end if;

  -- ponytail: recalcula a cada chamada (~0,1 s quente, ~4 s frio no ano
  -- inteiro); tabela de instantâneo se o limite anon de 3 s começar a cair.
  return query
  with comparison as materialized (
    select * from finance.contract_citation_comparison_v1(p_year)
  )
  select
    'approved'::text,
    latest_reviewed_at,
    latest_kind,
    'entity'::text,
    comparison.category,
    comparison.public_body,
    comparison.creditor_name,
    comparison.cited_number,
    (array_agg(comparison.cited_excerpt
      order by comparison.issue_date desc, comparison.commitment_key desc))[1],
    count(*)::integer,
    sum(comparison.payments)::integer,
    sum(comparison.unreadable_payments)::integer,
    to_char(sum(comparison.paid_amount), 'FM999999999990.00'),
    min(comparison.issue_date),
    max(comparison.issue_date),
    max(comparison.list_read_on),
    (array_agg(comparison.commitment_key
      order by comparison.issue_date desc, comparison.commitment_key desc))[1],
    max(comparison.pncp_url),
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'contract-citation-comparison/1.0.0'::text
  from comparison
  where comparison.creditor_is_entity
  group by comparison.category, comparison.public_body, comparison.creditor_name,
    comparison.cited_number
  union all
  -- Pessoa física: só o agregado por órgão, sem nome, número, trecho ou chave.
  select
    'approved'::text,
    latest_reviewed_at,
    latest_kind,
    'pf_aggregate'::text,
    comparison.category,
    comparison.public_body,
    null::text,
    null::text,
    null::text,
    count(*)::integer,
    sum(comparison.payments)::integer,
    sum(comparison.unreadable_payments)::integer,
    to_char(sum(comparison.paid_amount), 'FM999999999990.00'),
    min(comparison.issue_date),
    max(comparison.issue_date),
    max(comparison.list_read_on),
    null::text,
    null::text,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'contract-citation-comparison/1.0.0'::text
  from comparison
  where not comparison.creditor_is_entity
  group by comparison.category, comparison.public_body
  -- Sem ranking por valor: órgão, depois data.
  order by 6, 4, 14, 8;
end;
$function$;

revoke all on function api.get_public_contract_citations(integer) from public;
grant execute on function api.get_public_contract_citations(integer) to anon, authenticated;

comment on function api.get_public_contract_citations(integer) is
  'Citações de contrato em empenhos sem correspondência exata na lista do portal (ADR 0096). Devolve só o estado awaiting_review até a aprovação registrada desta versão; review_kind diz se a conferência foi humana ou automática por agente.';

commit;
