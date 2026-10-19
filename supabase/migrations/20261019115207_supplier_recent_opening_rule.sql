begin;

-- Indício "empresa recém-aberta com contrato relevante" (ADR 0097, ADR 0099).
-- Regra supplier-recent-opening/1.0.0: sociedade empresária (Ltda., S.A.,
-- EIRELI) cujo contrato com a Prefeitura começou até 180 dias depois da
-- abertura do CNPJ na Receita, com valor inicial de R$ 100 mil ou mais.
-- Ficam fora o empresário individual (MEI) e a sociedade unipessoal de
-- advocacia, formas comuns de contratar pessoa física por meio de PJ.
-- Contrato do PNCP igual a um do portal (mesmo CNPJ e valor) conta uma vez.
-- Abrir empresa e contratar com o poder público logo depois é lícito; o
-- padrão merece apuração (capacidade técnica, sócios, endereço).

insert into analysis.anomaly_rules (
  slug, version, name, description, deterministic_spec,
  implementation_version, severity, enabled
) values (
  'supplier-recent-opening', 1,
  'Empresa recém-aberta com contrato relevante',
  'Contrato de R$ 100 mil ou mais com empresa (sociedade empresária) aberta até 180 dias antes do início do contrato, segundo o cadastro da Receita Federal.',
  jsonb_build_object(
    'sources', jsonb_build_array('municipal_transparency_contratos', 'pncp_contrato', 'receita_cnpj_registry'),
    'max_days_after_opening', 180,
    'min_contract_value', 100000,
    'legal_natures', jsonb_build_array('2046', '2054', '2062', '2305'),
    'contract_start', 'vigencia_inicio (portal) ou dataAssinatura (PNCP)'
  ),
  'supplier-recent-opening/1.0.0', 'medium', true
)
on conflict (slug, version) do nothing;

create or replace function analysis.refresh_supplier_opening_signals()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  inserted_count integer;
begin
  with receita as (
    select distinct on (record.payload ->> 'cnpj')
      record.id as receita_record_id,
      record.payload ->> 'cnpj' as cnpj,
      to_date(record.payload ->> 'data_inicio_atividade', 'YYYYMMDD') as opened_on,
      record.payload ->> 'natureza_juridica' as legal_nature
    from raw.raw_records as record
    where record.record_type = 'receita_cnpj_registry'
      and record.payload ->> 'data_inicio_atividade'
        ~ '^(19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$'
    order by record.payload ->> 'cnpj', record.created_at desc, record.id desc
  ),
  portal_raw as (
    select distinct on (record.payload ->> 'id')
      record.id as contract_record_id,
      record.payload,
      regexp_replace(record.payload ->> 'documento', '\D', '', 'g') as cnpj,
      substring(record.payload ->> 'vigencia_inicio' from '^(\d{2})/\d{2}/\d{4}$')::integer as start_day,
      substring(record.payload ->> 'vigencia_inicio' from '^\d{2}/(\d{2})/\d{4}$')::integer as start_month,
      substring(record.payload ->> 'vigencia_inicio' from '^\d{2}/\d{2}/(\d{4})$')::integer as start_year,
      replace(replace(replace(btrim(record.payload ->> 'valor_contrato'), 'R$ ', ''), '.', ''), ',', '.') as value_text
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_contratos'
    order by record.payload ->> 'id', record.created_at desc, record.id desc
  ),
  portal as (
    select 'portal'::text as source, contract_record_id, cnpj,
      payload ->> 'contratoNumero' as contract_number,
      case
        when start_month between 1 and 12
          and start_day between 1 and extract(day from (
            make_date(start_year, start_month, 1) + interval '1 month - 1 day'
          ))::integer
        then make_date(start_year, start_month, start_day)
      end as contract_start,
      case when value_text ~ '^[0-9]+(\.[0-9]{1,2})?$' then value_text::numeric(20,2) end as contract_value
    from portal_raw
  ),
  pncp as (
    select distinct on (record.payload ->> 'numeroControlePNCP')
      'pncp'::text as source,
      record.id as contract_record_id,
      record.payload ->> 'niFornecedor' as cnpj,
      record.payload ->> 'numeroControlePNCP' as contract_number,
      case when record.payload ->> 'dataAssinatura' ~ '^\d{4}-\d{2}-\d{2}$'
        then (record.payload ->> 'dataAssinatura')::date end as contract_start,
      case when record.payload ->> 'valorGlobal' ~ '^[0-9]+(\.[0-9]+)?$'
        then round((record.payload ->> 'valorGlobal')::numeric, 2) end as contract_value
    from raw.raw_records as record
    where record.record_type = 'pncp_contrato'
      and record.payload ->> 'tipoPessoa' = 'PJ'
    order by record.payload ->> 'numeroControlePNCP', record.created_at desc, record.id desc
  ),
  contracts as (
    select * from portal
    union all
    select pncp.* from pncp
    where not exists (
      select 1 from portal
      where portal.cnpj = pncp.cnpj and portal.contract_value = pncp.contract_value
    )
  ),
  candidates as (
    select contract.*, receita.receita_record_id, receita.opened_on, receita.legal_nature,
      contract.contract_start - receita.opened_on as days_after_opening
    from contracts as contract
    join receita on receita.cnpj = contract.cnpj
    where contract.contract_start is not null
      and contract.contract_value >= 100000
      and receita.legal_nature in ('2046', '2054', '2062', '2305')
      and contract.contract_start >= receita.opened_on
      and contract.contract_start - receita.opened_on <= 180
  )
  insert into analysis.anomaly_findings (
    origin_raw_record_id, anomaly_rule_id, target_type, target_id, version,
    deterministic_inputs, deterministic_output, status, public_explanation
  )
  select
    candidate.contract_record_id,
    rule.id,
    'raw.raw_records',
    candidate.contract_record_id,
    1,
    jsonb_build_object(
      'source', candidate.source,
      'contract_number', candidate.contract_number,
      'supplier_cnpj', candidate.cnpj,
      'receita_record_id', candidate.receita_record_id,
      'legal_nature', candidate.legal_nature
    ),
    jsonb_build_object(
      'opened_on', candidate.opened_on,
      'contract_start', candidate.contract_start,
      'days_after_opening', candidate.days_after_opening,
      'contract_value', candidate.contract_value
    ),
    'triage',
    'A empresa foi aberta pouco antes de começar um contrato relevante com a Prefeitura. Empresas novas podem contratar com o poder público legalmente; o padrão merece apuração (capacidade técnica, sócios, endereço). Não é prova de irregularidade.'
  from candidates as candidate
  join analysis.anomaly_rules as rule
    on rule.slug = 'supplier-recent-opening' and rule.version = 1 and rule.enabled
  where not exists (
    select 1 from analysis.anomaly_findings as existing
    where existing.anomaly_rule_id = rule.id
      and existing.target_type = 'raw.raw_records'
      and existing.target_id = candidate.contract_record_id
  );
  get diagnostics inserted_count = row_count;

  -- Evidência: o registro do contrato (fonte primária) e o registro da
  -- Receita com a data de abertura.
  insert into evidence.evidence_items (
    target_type, target_id, raw_artifact_id, raw_record_id, evidence_kind,
    source_url, excerpt, locator, content_sha256, parser_version, is_primary
  )
  select 'analysis.anomaly_finding', finding.id, origin.raw_artifact_id,
    origin.id, 'source_record',
    case when origin.payload ->> 'url' ~ '^https://' then origin.payload ->> 'url'
      when artifact.source_url ~ '^https://' then artifact.source_url end,
    'Contrato com data de início e valor usados na regra.',
    jsonb_build_object('rule', 'supplier-recent-opening/1.0.0', 'role', 'contract'),
    artifact.sha256, 'supplier-recent-opening/1.0.0', true
  from analysis.anomaly_findings as finding
  join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
  join raw.raw_records as origin on origin.id = finding.origin_raw_record_id
  join raw.raw_artifacts as artifact on artifact.id = origin.raw_artifact_id
  where rule.slug = 'supplier-recent-opening'
    and not exists (
      select 1 from evidence.evidence_items as existing
      where existing.target_type = 'analysis.anomaly_finding'
        and existing.target_id = finding.id
        and existing.evidence_kind = 'source_record'
        and existing.raw_record_id = origin.id
    );

  insert into evidence.evidence_items (
    target_type, target_id, raw_artifact_id, raw_record_id, evidence_kind,
    source_url, excerpt, locator, content_sha256, parser_version, is_primary
  )
  select 'analysis.anomaly_finding', finding.id, receita.raw_artifact_id,
    receita.id, 'source_record',
    case when artifact.source_url ~ '^https://' then artifact.source_url end,
    'Cadastro da Receita Federal com a data de início de atividade.',
    jsonb_build_object('rule', 'supplier-recent-opening/1.0.0', 'role', 'receita'),
    artifact.sha256, 'supplier-recent-opening/1.0.0', false
  from analysis.anomaly_findings as finding
  join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
  join raw.raw_records as receita
    on receita.id = (finding.deterministic_inputs ->> 'receita_record_id')::uuid
  join raw.raw_artifacts as artifact on artifact.id = receita.raw_artifact_id
  where rule.slug = 'supplier-recent-opening'
    and not exists (
      select 1 from evidence.evidence_items as existing
      where existing.target_type = 'analysis.anomaly_finding'
        and existing.target_id = finding.id
        and existing.raw_record_id = receita.id
    );

  return inserted_count;
end;
$function$;

revoke all on function analysis.refresh_supplier_opening_signals() from public, anon, authenticated;

commit;
