begin;

-- ADR 0096 (emenda de 08/10/2026): a decisão vigente informa se foi humana ou
-- automática por agente (prefixo 'automated:' no reviewer_subject).

drop function finance.contract_citation_review_v1();
create function finance.contract_citation_review_v1()
returns table (decision text, reviewed_at timestamptz, review_kind text)
language sql
stable
set search_path = ''
as $function$
  select
    review.decision,
    review.reviewed_at,
    case when review.reviewer_subject like 'automated:%' then 'automated' else 'human' end
  from editorial.editorial_reviews as review
  where review.target_type = 'finance.contract_citation_comparison'
    and review.target_id = md5('contract-citation-comparison/1.0.0')::uuid
  order by review.reviewed_at desc, review.created_at desc, review.id desc
  limit 1
$function$;

revoke all on function finance.contract_citation_review_v1() from public, anon, authenticated;

commit;
