begin;

-- contract-citation-comparison/1.0.0 (ADR 0096): empenhos cujo histórico cita
-- um número de contrato que a regra do ADR 0086 não achou na lista de
-- contratos do portal (`nenhum_contrato`). É comparação, não acusação: o
-- público só vê o resultado depois que um revisor ativo conferir a amostra
-- no portal e registrar a aprovação desta versão.

create function finance.contract_citation_comparison_v1(p_year integer)
returns table (
  commitment_key text,
  commitment_raw_record_id uuid,
  issue_date date,
  public_body text,
  creditor_name text,
  creditor_is_entity boolean,
  cited_number text,
  cited_excerpt text,
  list_read_on date,
  paid_amount numeric,
  payments integer,
  unreadable_payments integer,
  category text,
  pncp_url text
)
language sql
stable
set search_path = ''
as $function$
  with latest_links as materialized (
    -- Vale a decisão mais recente de cada empenho, qualquer que seja o estado.
    select distinct on (link.commitment_key)
      link.commitment_key,
      link.commitment_raw_record_id,
      link.state,
      link.reason,
      link.cited_excerpt,
      link.decided_at
    from finance.commitment_contract_links as link
    order by link.commitment_key, link.decided_at desc, link.id desc
  ),
  citations as materialized (
    select
      link.commitment_key,
      link.commitment_raw_record_id,
      link.cited_excerpt,
      link.decided_at,
      regexp_match(upper(link.cited_excerpt),
        '([0-9]{1,5})\s*([A-Z]?)\s*(?:-\s*([A-Z]+))?\s*/\s*([0-9]{4})') as parts,
      to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') as issue_date,
      btrim(record.payload ->> 'field1082413') as public_body,
      btrim(record.payload ->> 'field1144629') as creditor_name
    from latest_links as link
    join raw.raw_records as record on record.id = link.commitment_raw_record_id
    where link.state = 'citacao_sem_confirmacao'
      and link.reason = 'nenhum_contrato'
      and record.payload ->> 'field1082407' ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
      and (p_year is null or right(record.payload ->> 'field1082407', 4) = p_year::text)
      -- A Câmara publica contratos em portal próprio, que não é coletado.
      and record.payload ->> 'field1082413' not ilike 'C%MARA MUNICIPAL%'
  ),
  payment_grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  paid as materialized (
    select
      payment.payload ->> 'field1082596' as commitment_key,
      sum(replace(replace(payment.payload ->> 'field1082592', '.', ''), ',', '.')::numeric)
        filter (where payment.payload ->> 'field1082592'
          ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$') as amount,
      count(*) filter (where payment.payload ->> 'field1082592'
          ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$')::integer
        as payments,
      count(*) filter (where coalesce(payment.payload ->> 'field1082592', '')
          !~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$')::integer
        as unreadable
    from raw.raw_records as payment
    join payment_grids as grid on grid.id = payment.raw_artifact_id
    where payment.record_type = 'municipal_payment_webrun'
      and payment.payload ->> 'field1082596' in (select c.commitment_key from citations as c)
    group by 1
  ),
  pncp as materialized (
    select distinct on (contract.parts[1]::integer, contract.parts[4], contract.supplier_key)
      contract.parts[1]::integer as sequence_number,
      contract.parts[4] as contract_year,
      contract.supplier_key,
      regexp_match(contract.control, '^([0-9]{14})-[0-9]+-([0-9]+)/([0-9]{4})$') as control
    from (
      select
        record.collected_at,
        record.payload ->> 'numeroControlePNCP' as control,
        regexp_match(upper(record.payload ->> 'numeroContratoEmpenho'),
          '([0-9]{1,5})\s*([A-Z]?)\s*(?:-\s*([A-Z]+))?\s*/\s*([0-9]{4})') as parts,
        finance.company_name_spelling_key(record.payload ->> 'nomeRazaoSocialFornecedor')
          as supplier_key
      from raw.raw_records as record
      where record.record_type = 'pncp_contrato'
    ) as contract
    where contract.parts is not null
      and contract.supplier_key is not null
    order by
      contract.parts[1]::integer,
      contract.parts[4],
      contract.supplier_key,
      contract.collected_at desc
  )
  select
    citation.commitment_key,
    citation.commitment_raw_record_id,
    citation.issue_date,
    citation.public_body,
    citation.creditor_name,
    -- MEI/ME com nome de pessoa conta como pessoa física: a sigla sozinha
    -- não basta para tratar o credor como empresa.
    finance.payment_creditor_is_entity_v1(citation.creditor_name)
      and finance.payment_creditor_is_entity_v1(
        regexp_replace(citation.creditor_name, '\m(ME|MEI|EPP|EIRELL?I)\M', ' ', 'gi')),
    coalesce(nullif(ltrim(citation.parts[1], '0'), ''), '0')
      || citation.parts[2]
      || coalesce('-' || citation.parts[3], '')
      || '/' || citation.parts[4],
    regexp_replace(citation.cited_excerpt,
      '[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}', '***.***.***-**', 'g'),
    (citation.decided_at at time zone 'America/Bahia')::date,
    coalesce(paid.amount, 0),
    coalesce(paid.payments, 0),
    coalesce(paid.unreadable, 0),
    case when pncp.control is null then 'sem_correspondencia' else 'publicado_no_pncp' end,
    case when pncp.control is not null then
      'https://pncp.gov.br/app/contratos/' || pncp.control[1] || '/' || pncp.control[3]
        || '/' || pncp.control[2]::integer
    end
  from citations as citation
  left join paid on paid.commitment_key = citation.commitment_key
  left join pncp
    on pncp.sequence_number = citation.parts[1]::integer
    and pncp.contract_year = citation.parts[4]
    and pncp.supplier_key = finance.company_name_spelling_key(citation.creditor_name)
  where citation.parts is not null
$function$;

revoke all on function finance.contract_citation_comparison_v1(integer) from public, anon, authenticated;

comment on function finance.contract_citation_comparison_v1(integer) is
  'contract-citation-comparison/1.0.0 (ADR 0096): por empenho, número de contrato citado sem correspondência exata na lista do portal, pago pela chave oficial e categoria PNCP. Uso interno; o público só lê pelo portão de revisão.';

-- A aprovação vale para uma versão da regra: nova versão, nova conferência.
create function finance.contract_citation_review_v1()
returns table (decision text, reviewed_at timestamptz)
language sql
stable
set search_path = ''
as $function$
  select review.decision, review.reviewed_at
  from editorial.editorial_reviews as review
  where review.target_type = 'finance.contract_citation_comparison'
    and review.target_id = md5('contract-citation-comparison/1.0.0')::uuid
  order by review.reviewed_at desc, review.created_at desc, review.id desc
  limit 1
$function$;

revoke all on function finance.contract_citation_review_v1() from public, anon, authenticated;

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
    'contract-citation-comparison/1.0.0'::text
  from chosen
  order by chosen.tier, chosen.seed_order;
end;
$function$;

revoke all on function api.get_contract_citation_review_sample() from public, anon;
grant execute on function api.get_contract_citation_review_sample() to authenticated;

comment on function api.get_contract_citation_review_sample() is
  'Amostra de conferência do ADR 0096 (só revisor ativo): exemplos da medição e 20 grupos por semente fixa, com nome do credor para conferir no portal.';

create function api.review_contract_citation_comparison(
  p_decision text,
  p_rationale text,
  p_checked_groups integer
)
returns table (decision text, reviewed_at timestamptz)
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid := (select auth.uid());
  normalized_rationale text := btrim(coalesce(p_rationale, ''));
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if p_decision is null
    or p_decision not in ('approved', 'changes_requested', 'rejected', 'withdrawn') then
    raise exception 'decisão inválida' using errcode = '22023';
  end if;
  if length(normalized_rationale) < 5 then
    raise exception 'justificativa obrigatória' using errcode = '22023';
  end if;
  if p_decision = 'approved' and coalesce(p_checked_groups, 0) < 1 then
    raise exception 'aprovação exige ao menos um grupo conferido no portal'
      using errcode = '22023';
  end if;

  return query
  insert into editorial.editorial_reviews as review (
    target_type,
    target_id,
    reviewer_subject,
    review_type,
    decision,
    rationale,
    checklist
  )
  values (
    'finance.contract_citation_comparison',
    md5('contract-citation-comparison/1.0.0')::uuid,
    reviewer_uid::text,
    'editorial',
    p_decision,
    normalized_rationale,
    jsonb_build_object(
      'methodology_version', 'contract-citation-comparison/1.0.0',
      'sample', 'exemplos da medição + 20 grupos por md5 de semente fixa',
      'checked_groups', coalesce(p_checked_groups, 0),
      'adr', '0096')
  )
  returning review.decision, review.reviewed_at;
end;
$function$;

revoke all on function api.review_contract_citation_comparison(text, text, integer)
  from public, anon;
grant execute on function api.review_contract_citation_comparison(text, text, integer)
  to authenticated;

comment on function api.review_contract_citation_comparison(text, text, integer) is
  'Registra a conferência humana da comparação do ADR 0096; a mais recente decide se a página pública mostra dados.';

create function api.get_public_contract_citations(p_year integer)
returns table (
  review_state text,
  approved_at timestamptz,
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
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;

  select review.decision, review.reviewed_at
  into latest_decision, latest_reviewed_at
  from finance.contract_citation_review_v1() as review;

  if latest_decision is distinct from 'approved' then
    return query select
      'awaiting_review'::text, null::timestamptz, 'status'::text, null::text, null::text,
      null::text, null::text, null::text, null::integer, null::integer, null::integer,
      null::text, null::date, null::date, null::date, null::text, null::text,
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
  order by 5, 3, 13, 7;
end;
$function$;

revoke all on function api.get_public_contract_citations(integer) from public;
grant execute on function api.get_public_contract_citations(integer) to anon, authenticated;

comment on function api.get_public_contract_citations(integer) is
  'Citações de contrato em empenhos sem correspondência exata na lista do portal (ADR 0096). Devolve só o estado awaiting_review até a aprovação registrada desta versão.';

commit;
