begin;

-- ADR 0088. A projeção pública passa a incluir as citações confirmadas por
-- revisão humana (última revisão 'approved', com o contrato escolhido no
-- checklist), rotuladas com review_mode 'human'. Retirada ('withdrawn')
-- continua valendo para os dois modos. Mesma assinatura e mesma versão de
-- metodologia: o site aceita os dois valores de review_mode desde o deploy
-- que acompanha esta migration.
create index editorial_reviews_commitment_link_contract_idx
  on editorial.editorial_reviews ((checklist ->> 'contract_portal_id'), reviewed_at desc)
  where target_type = 'finance.commitment_contract_links'
    and decision = 'approved';

create or replace function api.get_public_commitment_contract_links(
  contract_ids text[]
)
returns table (
  link_id uuid,
  contract_portal_id text,
  commitment_key text,
  commitment_number text,
  issue_date_text text,
  public_body text,
  creditor_name text,
  note_type text,
  amount_text text,
  cited_excerpt text,
  rule_version text,
  review_mode text,
  grid_artifact_sha256 text,
  grid_retrieved_at timestamptz,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if contract_ids is null
     or cardinality(contract_ids) < 1
     or cardinality(contract_ids) > 200 then
    raise exception 'contract_ids deve ter entre 1 e 200 ids'
      using errcode = '22023';
  end if;

  return query
  with automated as (
    select link.id, link.contract_portal_id, 'automated'::text as review_mode
    from finance.commitment_contract_links as link
    where link.state = 'ligado'
      and link.rule_version = 'commitment-contract-link/1.0.0'
      and link.contract_portal_id = any(contract_ids)
  ),
  human as (
    select distinct on (review.target_id)
      review.target_id as id,
      review.checklist ->> 'contract_portal_id' as contract_portal_id,
      'human'::text as review_mode
    from editorial.editorial_reviews as review
    where review.target_type = 'finance.commitment_contract_links'
      and review.decision = 'approved'
      and review.checklist ->> 'contract_portal_id' = any(contract_ids)
    order by review.target_id, review.reviewed_at desc, review.id desc
  ),
  published as (
    select * from automated
    union all
    select human.*
    from human
    join finance.commitment_contract_links as link
      on link.id = human.id
     and link.state = 'citacao_sem_confirmacao'
  )
  select
    link.id,
    published.contract_portal_id,
    link.commitment_key,
    record.payload ->> 'field1082410',
    record.payload ->> 'field1082407',
    record.payload ->> 'field1082413',
    record.payload ->> 'field1144629',
    record.payload ->> 'field1082409',
    record.payload ->> 'field1082412',
    link.cited_excerpt,
    link.rule_version,
    published.review_mode,
    artifact.sha256,
    artifact.retrieved_at,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'commitment-contract-links/1.0.0'::text
  from published
  join finance.commitment_contract_links as link
    on link.id = published.id
  join raw.raw_records as record
    on record.id = link.commitment_raw_record_id
  join raw.raw_artifacts as artifact
    on artifact.id = record.raw_artifact_id
  where not exists (
      select 1
      from raw.raw_records as newer
      where newer.record_type = 'municipal_commitment_webrun'
        and newer.source_record_key = record.source_record_key
        and (newer.collected_at, newer.id) > (record.collected_at, record.id)
    )
    and (
      published.review_mode = 'human'
      or coalesce(
        (
          select review.decision
          from editorial.editorial_reviews as review
          where review.target_type = 'finance.commitment_contract_links'
            and review.target_id = link.id
          order by review.reviewed_at desc, review.id desc
          limit 1
        ),
        'approved'
      ) <> 'withdrawn'
    )
    and (
      published.review_mode = 'automated'
      or (
        select review.decision
        from editorial.editorial_reviews as review
        where review.target_type = 'finance.commitment_contract_links'
          and review.target_id = link.id
        order by review.reviewed_at desc, review.id desc
        limit 1
      ) = 'approved'
    )
  order by
    published.contract_portal_id,
    to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') desc,
    link.commitment_key
  limit 2000;
end;
$function$;

commit;
