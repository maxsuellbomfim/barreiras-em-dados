begin;

-- ADR 0094. Citação de contrato com favorecido escrito de outro jeito (nome
-- fantasia no portal, razão social no empenho, sufixo LTDA-ME/EPP, empresário
-- individual) é confirmada quando o nome do credor no empenho é IGUAL, depois
-- de uma normalização fixa, à razão social, ao nome fantasia ou à razão social
-- seguida do nome fantasia do CNPJ do contrato citado no cadastro oficial da
-- Receita (ADR 0093). Só confirma; nunca rejeita por nome. Diferenças de
-- grafia (plural, letra trocada) continuam pendentes.

-- Normalização determinística: maiúsculas, sem acento, sem pontuação, sem as
-- formas jurídicas LTDA/LIMITADA/ME/EPP/EIRELI/MEI/S.A./S/S.
create function finance.normalize_company_name(p_name text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select nullif(btrim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
    regexp_replace(
      translate(
        upper(coalesce(p_name, '')),
        'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
        'AAAAAEEEEIIIIOOOOOUUUUCN'
      ),
      '\mS\s*[/.]\s*[AS]\M\.?', ' ', 'g'),
    '\.', '', 'g'),
    '[^A-Z0-9]+', ' ', 'g'),
    '\m(LTDA|LIMITADA|ME|EPP|EIRELI|EIRELLI|MEI|SA)\M', ' ', 'g'),
    '\s+', ' ', 'g')), '')
$$;

create function finance.confirm_commitment_links_by_registry_name()
returns table (decision text, decided integer)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  confirmed integer;
begin
  perform pg_advisory_xact_lock(hashtext('commitment-registry-name'));

  create temporary table registry_name_candidates on commit drop as
  select
    link.id as link_id,
    link.reason,
    link.rule_version,
    commitment.payload ->> 'field1144629' as creditor_name,
    finance.normalize_company_name(commitment.payload ->> 'field1144629') as creditor_key,
    candidate.contract_raw_record_id,
    candidate.contract_portal_id,
    candidate.contract_number,
    candidate.contractor,
    registry.cnpj,
    registry.razao_social,
    registry.nome_fantasia,
    registry.registry_month,
    registry.raw_record_id as registry_raw_record_id,
    case
      when finance.normalize_company_name(commitment.payload ->> 'field1144629')
        = finance.normalize_company_name(registry.razao_social)
      then 'razao_social'
      when finance.normalize_company_name(commitment.payload ->> 'field1144629')
        = finance.normalize_company_name(registry.nome_fantasia)
      then 'nome_fantasia'
      when finance.normalize_company_name(commitment.payload ->> 'field1144629')
        = finance.normalize_company_name(
            registry.razao_social || ' ' || registry.nome_fantasia)
      then 'razao_social_e_nome_fantasia'
    end as matched_field
  from finance.commitment_contract_links as link
  join raw.raw_records as commitment on commitment.id = link.commitment_raw_record_id
  join finance.commitment_link_candidates as candidate on candidate.link_id = link.id
  join raw.raw_records as contract on contract.id = candidate.contract_raw_record_id
  join finance.cnpj_registry_latest() as registry
    on registry.cnpj = regexp_replace(contract.payload ->> 'documento', '[^0-9]', '', 'g')
  where link.state = 'citacao_sem_confirmacao'
    and link.reason in ('favorecido_divergente', 'varios_contratos')
    and finance.normalize_company_name(commitment.payload ->> 'field1144629') is not null
    and coalesce((
      select review.decision
      from editorial.editorial_reviews as review
      where review.target_type = 'finance.commitment_contract_links'
        and review.target_id = link.id
      order by review.reviewed_at desc, review.id desc
      limit 1
    ), 'pending') in ('pending', 'changes_requested');

  -- Confirma: exatamente um contrato candidato cujo CNPJ tem esse nome.
  with matched as (
    select * from registry_name_candidates where matched_field is not null
  ), chosen as (
    select matched.*
    from matched
    where (
      select count(distinct other.contract_raw_record_id)
      from matched as other
      where other.link_id = matched.link_id
    ) = 1
  ), inserted as (
    insert into editorial.editorial_reviews (
      target_type, target_id, reviewer_subject, review_type, decision,
      rationale, checklist
    )
    select distinct on (chosen.link_id)
      'finance.commitment_contract_links',
      chosen.link_id,
      'automated:commitment-registry-name',
      'data_quality',
      'approved',
      'O nome do credor no empenho é o mesmo (sem acento, pontuação e forma '
        || 'jurídica) da ' || replace(chosen.matched_field, '_', ' ')
        || ' registrada na Receita para o CNPJ do contrato citado.',
      jsonb_build_object(
        'reason', chosen.reason,
        'rule_version', chosen.rule_version,
        'key_rule_version', 'commitment-registry-name/1.0.0',
        'creditor_name', chosen.creditor_name,
        'matched_field', chosen.matched_field,
        'cnpj', chosen.cnpj,
        'registry_month', chosen.registry_month,
        'registry_raw_record_id', chosen.registry_raw_record_id,
        'contract_raw_record_id', chosen.contract_raw_record_id,
        'contract_portal_id', chosen.contract_portal_id,
        'contract_number', chosen.contract_number,
        'contractor', chosen.contractor
      )
    from chosen
    order by chosen.link_id
    returning 1
  )
  select count(*)::integer into confirmed from inserted;

  if confirmed > 0 then
    insert into audit.audit_events (
      actor_type, actor_subject, action, target_type, target_id,
      after_state, metadata
    ) values (
      'worker',
      'commitment-registry-name',
      'commitment_links.decided_by_registry_name',
      'finance.commitment_contract_links',
      null,
      jsonb_build_object('approved', confirmed),
      jsonb_build_object(
        'version', 'commitment-registry-name/1.0.0',
        'records_deleted', false
      )
    );
  end if;

  return query values ('approved'::text, confirmed);
end;
$$;

revoke all on function finance.normalize_company_name(text) from public, anon;
revoke all on function finance.confirm_commitment_links_by_registry_name()
  from public, anon, authenticated, service_role;
grant execute on function finance.confirm_commitment_links_by_registry_name()
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
        -- ADR 0094: nome do empenho igual à razão social ou ao nome fantasia
        -- do CNPJ do contrato no cadastro oficial da Receita.
        when review.reviewer_subject = 'automated:commitment-registry-name'
        then 'registry_name'
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

commit;
