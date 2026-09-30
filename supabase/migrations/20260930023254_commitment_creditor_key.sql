begin;

-- ADR 0090. Citações de contrato com favorecido divergente (ou vários
-- contratos) se resolvem por chave oficial quando o código do credor no
-- sistema da Prefeitura já está ligado, pela regra exata, a um único CNPJ:
-- confirma se exatamente um contrato citado tem esse CNPJ; rejeita se
-- nenhum candidato tem. A decisão vai para editorial.editorial_reviews com o
-- autor 'automated:commitment-creditor-key' e a evidência no checklist; a
-- fila humana já exclui itens decididos. Nada é apagado.

create function finance.confirm_commitment_links_by_creditor_key()
returns table (decision text, decided integer)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  confirmed integer;
  rejected integer;
begin
  perform pg_advisory_xact_lock(hashtext('commitment-creditor-key'));

  create temporary table creditor_key_map on commit drop as
  select
    commitment.payload ->> 'field1144633' as creditor_code,
    min(regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g')) as cnpj,
    count(distinct regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g'))
      as cnpjs,
    count(*)::integer as evidence_links
  from finance.commitment_contract_links as link
  join raw.raw_records as commitment on commitment.id = link.commitment_raw_record_id
  join raw.raw_records as contract on contract.id = link.contract_raw_record_id
  where link.state = 'ligado'
    and link.rule_version = 'commitment-contract-link/1.0.0'
    and commitment.payload ->> 'field1144633' ~ '^[0-9]{1,12}$'
    and regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g')
      ~ '^[0-9]{13,14}$'
  group by 1;

  create temporary table creditor_key_pending on commit drop as
  select
    link.id as link_id,
    link.reason,
    link.rule_version,
    map.cnpj,
    map.evidence_links,
    commitment.payload ->> 'field1144633' as creditor_code,
    candidate.contract_raw_record_id,
    candidate.contract_portal_id,
    candidate.contract_number,
    candidate.contractor,
    regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g')
      as candidate_cnpj
  from finance.commitment_contract_links as link
  join raw.raw_records as commitment on commitment.id = link.commitment_raw_record_id
  join creditor_key_map as map
    on map.creditor_code = commitment.payload ->> 'field1144633'
   and map.cnpjs = 1
  join finance.commitment_link_candidates as candidate on candidate.link_id = link.id
  join raw.raw_records as contract on contract.id = candidate.contract_raw_record_id
  where link.state = 'citacao_sem_confirmacao'
    and link.reason in ('favorecido_divergente', 'varios_contratos')
    and coalesce((
      select review.decision
      from editorial.editorial_reviews as review
      where review.target_type = 'finance.commitment_contract_links'
        and review.target_id = link.id
      order by review.reviewed_at desc, review.id desc
      limit 1
    ), 'pending') in ('pending', 'changes_requested');

  -- Confirma: exatamente um candidato com o CNPJ do credor.
  with chosen as (
    select pending.*
    from creditor_key_pending as pending
    where pending.candidate_cnpj = pending.cnpj
      and (
        select count(*) from creditor_key_pending as other
        where other.link_id = pending.link_id and other.candidate_cnpj = pending.cnpj
      ) = 1
  ), inserted as (
    insert into editorial.editorial_reviews (
      target_type, target_id, reviewer_subject, review_type, decision,
      rationale, checklist
    )
    select
      'finance.commitment_contract_links',
      chosen.link_id,
      'automated:commitment-creditor-key',
      'data_quality',
      'approved',
      'O código do credor no sistema da Prefeitura já está ligado, pela regra '
        || 'exata, somente a este CNPJ, que é o do contrato citado.',
      jsonb_build_object(
        'reason', chosen.reason,
        'rule_version', chosen.rule_version,
        'key_rule_version', 'commitment-creditor-key/1.0.0',
        'creditor_code', chosen.creditor_code,
        'cnpj', chosen.cnpj,
        'evidence_links', chosen.evidence_links,
        'contract_raw_record_id', chosen.contract_raw_record_id,
        'contract_portal_id', chosen.contract_portal_id,
        'contract_number', chosen.contract_number,
        'contractor', chosen.contractor
      )
    from chosen
    returning 1
  )
  select count(*)::integer into confirmed from inserted;

  -- Rejeita: nenhum candidato tem o CNPJ do credor (é outra empresa).
  with different as (
    select distinct on (pending.link_id) pending.*
    from creditor_key_pending as pending
    where not exists (
      select 1 from creditor_key_pending as other
      where other.link_id = pending.link_id and other.candidate_cnpj = other.cnpj
    )
    order by pending.link_id
  ), inserted as (
    insert into editorial.editorial_reviews (
      target_type, target_id, reviewer_subject, review_type, decision,
      rationale, checklist
    )
    select
      'finance.commitment_contract_links',
      different.link_id,
      'automated:commitment-creditor-key',
      'data_quality',
      'rejected',
      'O código do credor no sistema da Prefeitura está ligado, pela regra '
        || 'exata, a outro CNPJ; o contrato citado é de outra empresa.',
      jsonb_build_object(
        'reason', different.reason,
        'rule_version', different.rule_version,
        'key_rule_version', 'commitment-creditor-key/1.0.0',
        'creditor_code', different.creditor_code,
        'cnpj', different.cnpj,
        'evidence_links', different.evidence_links
      )
    from different
    returning 1
  )
  select count(*)::integer into rejected from inserted;

  if confirmed + rejected > 0 then
    insert into audit.audit_events (
      actor_type, actor_subject, action, target_type, target_id,
      after_state, metadata
    ) values (
      'worker',
      'commitment-creditor-key',
      'commitment_links.decided_by_creditor_key',
      'finance.commitment_contract_links',
      null,
      jsonb_build_object('approved', confirmed, 'rejected', rejected),
      jsonb_build_object(
        'version', 'commitment-creditor-key/1.0.0',
        'records_deleted', false
      )
    );
  end if;

  return query values ('approved'::text, confirmed), ('rejected'::text, rejected);
end;
$$;

revoke all on function finance.confirm_commitment_links_by_creditor_key()
  from public, anon, authenticated, service_role;
grant usage on schema finance to collector_worker;
grant execute on function finance.confirm_commitment_links_by_creditor_key()
  to collector_worker;

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
      -- ADR 0090: confirmação por chave oficial (código do credor -> CNPJ)
      -- é decisão automática e sai com rótulo próprio.
      case
        when review.reviewer_subject = 'automated:commitment-creditor-key'
        then 'creditor_key'
        else 'human'
      end::text as review_mode
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
      published.review_mode <> 'automated'
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

select * from finance.confirm_commitment_links_by_creditor_key();

commit;
