begin;

-- ADR 0096: a comparação recalculada a cada chamada levava 2,4–4,6 s fria
-- (7 mil leituras do bruto com descompressão do payload; limite anon de 3 s).
-- O instantâneo guarda o resultado de contract_citation_comparison_v1(null) e
-- é refeito de hora em hora pelo pg_cron; as funções públicas leem daqui.
-- O índice parcial tentado antes não vira varredura só por índice (o filtro
-- referencia a coluna payload inteira) e só encareceria as inserções.
drop index if exists raw.raw_records_commitment_citation_idx;

create table finance.contract_citation_snapshot (
  commitment_key text primary key check (commitment_key ~ '^[OE]-[0-9]+$'),
  commitment_raw_record_id uuid not null references raw.raw_records(id),
  issue_date date not null,
  public_body text not null,
  creditor_name text not null,
  creditor_is_entity boolean not null,
  cited_number text not null,
  cited_excerpt text not null,
  list_read_on date not null,
  paid_amount numeric not null,
  payments integer not null,
  unreadable_payments integer not null,
  category text not null check (category in ('sem_correspondencia', 'publicado_no_pncp')),
  pncp_url text,
  computed_at timestamptz not null
);

alter table finance.contract_citation_snapshot enable row level security;
alter table finance.contract_citation_snapshot force row level security;
revoke all on finance.contract_citation_snapshot from anon, authenticated;

comment on table finance.contract_citation_snapshot is
  'Instantâneo de finance.contract_citation_comparison_v1(null) (ADR 0096), refeito de hora em hora; cache de leitura, não registro.';

create function finance.refresh_contract_citation_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  refreshed integer;
begin
  perform pg_advisory_xact_lock(hashtext('finance.contract_citation_snapshot'));
  delete from finance.contract_citation_snapshot;
  insert into finance.contract_citation_snapshot (
    commitment_key, commitment_raw_record_id, issue_date, public_body, creditor_name,
    creditor_is_entity, cited_number, cited_excerpt, list_read_on, paid_amount, payments,
    unreadable_payments, category, pncp_url, computed_at
  )
  select
    comparison.commitment_key, comparison.commitment_raw_record_id, comparison.issue_date,
    comparison.public_body, comparison.creditor_name, comparison.creditor_is_entity,
    comparison.cited_number, comparison.cited_excerpt, comparison.list_read_on,
    comparison.paid_amount, comparison.payments, comparison.unreadable_payments,
    comparison.category, comparison.pncp_url, now()
  from finance.contract_citation_comparison_v1(null) as comparison;
  get diagnostics refreshed = row_count;
  return refreshed;
end;
$function$;

revoke all on function finance.refresh_contract_citation_snapshot()
  from public, anon, authenticated;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-contract-citation-snapshot', '35 * * * *',
      'select finance.refresh_contract_citation_snapshot()');
  end if;
end;
$schedule$;

create or replace function api.get_contract_citation_review_sample()
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
    from finance.contract_citation_snapshot as comparison
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

create or replace function api.get_public_contract_citations(p_year integer)
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

  return query
  with comparison as (
    select *
    from finance.contract_citation_snapshot as snapshot
    where snapshot.issue_date >= make_date(p_year, 1, 1)
      and snapshot.issue_date < make_date(p_year + 1, 1, 1)
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

commit;
