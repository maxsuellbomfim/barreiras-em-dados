begin;

-- ADR 0088. Fila de revisão humana das citações de contrato que a regra não
-- confirmou (favorecido divergente ou mais de um contrato com o número).
-- Os candidatos vêm da própria regra determinística (worker de
-- reconciliação), não de reimplementação em SQL. A decisão humana fica em
-- editorial.editorial_reviews, uma linha por ligação, com o contrato escolhido
-- e a justificativa; nada aqui publica.
create table finance.commitment_link_candidates (
  link_id uuid not null references finance.commitment_contract_links(id),
  contract_raw_record_id uuid not null references raw.raw_records(id),
  contract_portal_id text not null,
  contract_number text not null,
  contractor text not null,
  created_at timestamptz not null default now(),
  primary key (link_id, contract_raw_record_id)
);

create index commitment_link_candidates_contract_idx
  on finance.commitment_link_candidates (contract_raw_record_id);

alter table finance.commitment_link_candidates enable row level security;
alter table finance.commitment_link_candidates force row level security;
revoke all on finance.commitment_link_candidates from anon, authenticated;
grant select, insert on finance.commitment_link_candidates to collector_worker;

create policy collector_worker_commitment_link_candidates_select
  on finance.commitment_link_candidates
  for select to collector_worker
  using (true);

create policy collector_worker_commitment_link_candidates_insert
  on finance.commitment_link_candidates
  for insert to collector_worker
  with check (true);

create trigger reject_mutation
before update or delete on finance.commitment_link_candidates
for each row execute function audit.reject_mutation();

create index editorial_reviews_commitment_link_idx
  on editorial.editorial_reviews (target_id, reviewed_at desc)
  where target_type = 'finance.commitment_contract_links';

-- Grupos pendentes: mesmo motivo, mesmo favorecido e mesmo(s) contrato(s)
-- candidato(s). Uma decisão vale para todo o grupo, mas é gravada por ligação.
create function api.get_commitment_link_review_groups(
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
      link.cited_excerpt,
      record.payload,
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
      md5(pending.reason || '|' || (pending.payload ->> 'field1144629') || '|' || pending.candidate_ids)
        as group_key,
      pending.reason,
      pending.payload ->> 'field1144629' as creditor_name,
      pending.candidate_ids,
      count(*)::integer as pending_count,
      array_agg(pending.id order by pending.issue_date desc, pending.id) as link_ids,
      min(pending.issue_date) as first_issue_date,
      max(pending.issue_date) as last_issue_date
    from pending
    where pending.candidate_ids is not null
    group by 1, 2, 3, 4
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
  from groups as grouped
  order by grouped.pending_count desc, grouped.group_key
  limit page_size;
end;
$function$;

revoke all on function api.get_commitment_link_review_groups(integer) from public, anon;
grant execute on function api.get_commitment_link_review_groups(integer) to authenticated;

create function api.review_commitment_link_group(
  p_link_ids uuid[],
  p_review_decision text,
  p_contract_raw_record_id uuid default null,
  p_review_note text default null
)
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid := (select auth.uid());
  expected integer;
  eligible integer;
  inserted integer;
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if p_review_decision not in ('approved', 'rejected', 'changes_requested') then
    raise exception 'decisão inválida' using errcode = '22023';
  end if;
  if length(btrim(coalesce(p_review_note, ''))) < 5 then
    raise exception 'toda decisão exige justificativa' using errcode = '22023';
  end if;
  if p_link_ids is null
     or cardinality(p_link_ids) < 1
     or cardinality(p_link_ids) > 5000 then
    raise exception 'o grupo deve ter entre 1 e 5000 ligações' using errcode = '22023';
  end if;
  if (p_review_decision = 'approved') <> (p_contract_raw_record_id is not null) then
    raise exception 'confirmar exige o contrato escolhido; rejeitar não aceita contrato'
      using errcode = '22023';
  end if;

  expected := cardinality(array(select distinct unnest(p_link_ids)));

  select count(*) into eligible
  from finance.commitment_contract_links as link
  where link.id = any(p_link_ids)
    and link.state = 'citacao_sem_confirmacao'
    and link.reason in ('favorecido_divergente', 'varios_contratos')
    -- Pedido de evidência não encerra o item; aprovar ou rejeitar, sim.
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
    and (
      p_contract_raw_record_id is null
      or exists (
        select 1
        from finance.commitment_link_candidates as candidate
        where candidate.link_id = link.id
          and candidate.contract_raw_record_id = p_contract_raw_record_id
      )
    );
  if eligible <> expected then
    raise exception 'há ligações já revisadas, fora da fila ou sem esse contrato candidato'
      using errcode = '42501';
  end if;

  insert into editorial.editorial_reviews (
    target_type, target_id, reviewer_subject, review_type, decision,
    rationale, checklist
  )
  select
    'finance.commitment_contract_links',
    link.id,
    reviewer_uid::text,
    'data_quality',
    p_review_decision,
    btrim(p_review_note),
    jsonb_strip_nulls(jsonb_build_object(
      'reason', link.reason,
      'rule_version', link.rule_version,
      'group_size', expected,
      'contract_raw_record_id', candidate.contract_raw_record_id,
      'contract_portal_id', candidate.contract_portal_id,
      'contract_number', candidate.contract_number,
      'contractor', candidate.contractor
    ))
  from finance.commitment_contract_links as link
  left join finance.commitment_link_candidates as candidate
    on candidate.link_id = link.id
   and candidate.contract_raw_record_id = p_contract_raw_record_id
  where link.id = any(p_link_ids);
  get diagnostics inserted = row_count;
  return inserted;
end;
$function$;

revoke all on function api.review_commitment_link_group(uuid[], text, uuid, text)
  from public, anon;
grant execute on function api.review_commitment_link_group(uuid[], text, uuid, text)
  to authenticated;

commit;
