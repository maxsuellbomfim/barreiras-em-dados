begin;

-- Projeção pública de indícios (ADR 0099): só achados com revisão aprovada
-- mais recente. O nome da empresa vem sempre da razão social do cadastro da
-- Receita: o campo "favorecido" do portal às vezes traz o nome de uma pessoa
-- física (sócio), que não deve aparecer associado a um indício.
create or replace function api.get_public_indicios(page_size integer default 100)
returns table (
  finding_id uuid,
  rule_slug text,
  rule_name text,
  rule_description text,
  rule_methodology text,
  severity text,
  public_explanation text,
  review_rationale text,
  review_kind text,
  reviewed_at timestamptz,
  supplier_name text,
  supplier_cnpj text,
  contract_number text,
  contract_object text,
  contract_value numeric,
  contract_start date,
  opened_on date,
  days_after_opening integer,
  amendments_value numeric,
  contract_source_url text,
  contract_artifact_sha256 text,
  registry_artifact_sha256 text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200' using errcode = '22023';
  end if;

  return query
  select
    finding.id,
    rule.slug,
    rule.name,
    rule.description,
    rule.implementation_version,
    rule.severity,
    finding.public_explanation,
    review.rationale,
    case when review.reviewer_subject like 'automated:%' then 'automated' else 'human' end,
    review.reviewed_at,
    registry.payload ->> 'razao_social',
    finding.deterministic_inputs ->> 'supplier_cnpj',
    finding.deterministic_inputs ->> 'contract_number',
    nullif(btrim(contract.payload ->> 'contratoObjeto'), ''),
    (finding.deterministic_output ->> 'contract_value')::numeric(20,2),
    (finding.deterministic_output ->> 'contract_start')::date,
    (finding.deterministic_output ->> 'opened_on')::date,
    (finding.deterministic_output ->> 'days_after_opening')::integer,
    case when contract.payload ->> 'aditivos_valor_total' ~ '^[0-9]+(\.[0-9]{1,2})?$'
      then (contract.payload ->> 'aditivos_valor_total')::numeric(20,2) end,
    case when contract.payload ->> 'url' ~ '^https://' then contract.payload ->> 'url' end,
    contract_artifact.sha256,
    registry_artifact.sha256,
    'public-indicios/1.0.0'::text
  from analysis.anomaly_findings as finding
  join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
  join lateral (
    select latest.decision, latest.rationale, latest.reviewer_subject, latest.reviewed_at
    from editorial.editorial_reviews as latest
    where latest.target_type = 'analysis.anomaly_finding'
      and latest.target_id = finding.id
    order by latest.reviewed_at desc, latest.created_at desc, latest.id desc
    limit 1
  ) as review on review.decision = 'approved'
  join raw.raw_records as contract on contract.id = finding.origin_raw_record_id
  join raw.raw_artifacts as contract_artifact on contract_artifact.id = contract.raw_artifact_id
  join raw.raw_records as registry
    on registry.id = (finding.deterministic_inputs ->> 'receita_record_id')::uuid
  join raw.raw_artifacts as registry_artifact on registry_artifact.id = registry.raw_artifact_id
  where rule.slug = 'supplier-recent-opening'
    and finding.supersedes_id is null
    and finding.status in ('triage', 'needs_context', 'confirmed_as_signal')
  order by (finding.deterministic_output ->> 'contract_start')::date desc, finding.id
  limit page_size;
end;
$function$;

revoke all on function api.get_public_indicios(integer) from public;
grant execute on function api.get_public_indicios(integer) to anon, authenticated;

comment on function api.get_public_indicios(integer) is
  'Indícios publicados após revisão automatizada registrada (ADR 0099): só o que tem revisão aprovada mais recente; indício, não prova de irregularidade (public-indicios/1.0.0).';

notify pgrst, 'reload schema';

commit;
