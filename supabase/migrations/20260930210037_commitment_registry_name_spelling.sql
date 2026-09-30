begin;

-- ADR 0094, régua commitment-registry-name/1.1.0. A 1.0.0 exigia igualdade
-- depois da normalização fixa e deixou pendentes diferenças só de grafia
-- ("CARTUCHOS" x "CARTUCHO", "DE" x "DOS", "J S" x "JS", EIRELI -> LTDA).
-- A chave de grafia parte da mesma normalização e ainda remove as
-- preposições DE/DA/DO/DAS/DOS/E, o S final de cada palavra e os espaços.
-- Continua exigindo o CNPJ oficial do contrato citado e um único contrato
-- candidato com o nome; só confirma, nunca rejeita. Letra trocada no meio
-- ("MATERIAS" x "MATERIAIS") segue pendente.

create function finance.company_name_spelling_key(p_name text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select nullif(replace(regexp_replace(regexp_replace(
    coalesce(finance.normalize_company_name(p_name), ''),
    '\m(DE|DA|DO|DAS|DOS|E)\M', ' ', 'g'),
    'S\M', '', 'g'), ' ', ''), '')
$$;

revoke all on function finance.company_name_spelling_key(text) from public, anon;

create or replace function finance.confirm_commitment_links_by_registry_name()
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
      -- 1.1.0: mesma comparação pela chave de grafia (plural, preposição,
      -- espaço entre iniciais); rótulo próprio na evidência.
      when finance.company_name_spelling_key(commitment.payload ->> 'field1144629')
        = finance.company_name_spelling_key(registry.razao_social)
      then 'razao_social_grafia'
      when finance.company_name_spelling_key(commitment.payload ->> 'field1144629')
        = finance.company_name_spelling_key(registry.nome_fantasia)
      then 'nome_fantasia_grafia'
      when finance.company_name_spelling_key(commitment.payload ->> 'field1144629')
        = finance.company_name_spelling_key(
            registry.razao_social || ' ' || registry.nome_fantasia)
      then 'razao_social_e_nome_fantasia_grafia'
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
      case
        when chosen.matched_field like '%\_grafia' then
          'O nome do credor no empenho é o mesmo (sem acento, pontuação, forma '
            || 'jurídica, preposições, plural e espaços) da '
            || replace(replace(chosen.matched_field, '_grafia', ''), '_', ' ')
            || ' registrada na Receita para o CNPJ do contrato citado.'
        else
          'O nome do credor no empenho é o mesmo (sem acento, pontuação e forma '
            || 'jurídica) da ' || replace(chosen.matched_field, '_', ' ')
            || ' registrada na Receita para o CNPJ do contrato citado.'
      end,
      jsonb_build_object(
        'reason', chosen.reason,
        'rule_version', chosen.rule_version,
        'key_rule_version', 'commitment-registry-name/1.1.0',
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
        'version', 'commitment-registry-name/1.1.0',
        'records_deleted', false
      )
    );
  end if;

  return query values ('approved'::text, confirmed);
end;
$$;

commit;
