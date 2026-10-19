begin;

-- ADR 0099: sinais financeiros passam por revisão automatizada registrada.
-- Conferência de 19/10/2026 dos 116 sinais "mais de um relatório no mesmo
-- período" (regra v1), todos em triagem e visíveis em /financas:
--   101 = o mesmo documento oficial normalizado duas vezes pelo nosso
--         processamento (mesmo hash, mesmos totais);
--   4   = idem, com o documento ligado a duas origens;
--   11  = portal (consolidado, inclui a Câmara) × TCM-BA (só Executivo) do
--         mesmo mês, escopos diferentes já reconciliados no fechamento
--         (ADR 0098).
-- Nenhum era indício sobre a Prefeitura. A regra v2 só dispara quando a
-- mesma fonte publica dois documentos distintos com totais diferentes para o
-- mesmo órgão e período (republicação divergente, que pede reconciliação).

insert into analysis.anomaly_rules (
  slug, version, name, description, deterministic_spec,
  implementation_version, severity, enabled
) values (
  'finance-duplicate-period', 2,
  'Documentos divergentes para o mesmo período',
  'A mesma fonte publicou dois ou mais documentos oficiais distintos para o mesmo órgão e período, com totais diferentes. Uma das versões pode ser retificação; a soma exige reconciliação.',
  jsonb_build_object(
    'filters', jsonb_build_array('validation_status = validated', 'published_at is not null'),
    'group_by', jsonb_build_array('public_body_id', 'fiscal_year', 'period_start', 'period_end', 'fonte de origem'),
    'condition', 'count(distinct source_document_artifact_id) > 1 and count(distinct totais) > 1',
    'source_table', 'finance.expense_reports'
  ),
  'finance-anomaly-rules/1.1.0', 'medium', true
)
on conflict (slug, version) do nothing;

update analysis.anomaly_rules
set enabled = false
where slug = 'finance-duplicate-period' and version = 1;

-- Conferência por código (primeira camada da revisão automatizada). Rejeita,
-- com motivo registrado, o que tem explicação verificável; o restante fica
-- para a conferência do agente, que registra a decisão final.
create or replace function analysis.review_finance_signals()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  recorded integer;
begin
  with findings as (
    select finding.id, rule.slug, rule.version as rule_version,
      report.id as report_id, report.public_body_id, report.fiscal_year,
      report.period_start, report.period_end
    from analysis.anomaly_findings as finding
    join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
    join finance.expense_reports as report
      on finding.target_type = 'finance.expense_report'
     and report.id = finding.target_id
    where finding.supersedes_id is null
      and finding.status in ('triage', 'needs_context', 'confirmed_as_signal')
      and not exists (
        select 1 from editorial.editorial_reviews as review
        where review.target_type = 'analysis.anomaly_finding'
          and review.target_id = finding.id
          and review.reviewer_subject like 'automated:finance-signal-review/%'
      )
  ),
  peers as (
    select finding.id,
      count(*) as peer_reports,
      count(distinct peer.source_document_artifact_id) as distinct_documents,
      count(distinct source.slug) as distinct_sources,
      array_agg(distinct source.slug order by source.slug) as sources,
      max(per_source.documents) as max_documents_per_source
    from findings as finding
    join finance.expense_reports as peer
      on peer.public_body_id = finding.public_body_id
     and peer.fiscal_year = finding.fiscal_year
     and peer.period_start = finding.period_start
     and peer.period_end = finding.period_end
     and peer.validation_status = 'validated'
     and peer.published_at is not null
    join raw.raw_records as origin on origin.id = peer.origin_raw_record_id
    join raw.raw_artifacts as origin_artifact on origin_artifact.id = origin.raw_artifact_id
    join source.source_endpoints as endpoint on endpoint.id = origin_artifact.source_endpoint_id
    join source.data_sources as source on source.id = endpoint.data_source_id
    cross join lateral (
      select count(distinct same_source.source_document_artifact_id) as documents
      from finance.expense_reports as same_source
      join raw.raw_records as same_origin on same_origin.id = same_source.origin_raw_record_id
      join raw.raw_artifacts as same_artifact on same_artifact.id = same_origin.raw_artifact_id
      join source.source_endpoints as same_endpoint on same_endpoint.id = same_artifact.source_endpoint_id
      where same_endpoint.data_source_id = endpoint.data_source_id
        and same_source.public_body_id = finding.public_body_id
        and same_source.fiscal_year = finding.fiscal_year
        and same_source.period_start = finding.period_start
        and same_source.period_end = finding.period_end
        and same_source.validation_status = 'validated'
        and same_source.published_at is not null
    ) as per_source
    where finding.slug = 'finance-duplicate-period'
    group by finding.id
  ),
  classified as (
    select finding.id,
      case
        when finding.slug = 'finance-duplicate-period' and peers.distinct_documents <= 1
          then 'same_document'
        when finding.slug = 'finance-duplicate-period'
          and peers.distinct_sources > 1
          and peers.max_documents_per_source = 1
          and peers.sources <@ array['prefeitura-barreiras-transparencia', 'tcm-ba']
          then 'portal_tcm_scope'
        when finding.slug = 'finance-accounting-consistency' and not (
          report.total_paid_to_date_amount > report.total_committed_to_date_amount
          or report.total_liquidated_to_date_amount > report.total_committed_to_date_amount
          or least(
            report.total_updated_amount, report.total_committed_period_amount,
            report.total_committed_to_date_amount, report.total_liquidated_period_amount,
            report.total_liquidated_to_date_amount, report.total_paid_period_amount,
            report.total_paid_to_date_amount, report.total_balance_amount
          ) < 0
        ) then 'condition_not_met'
      end as classification,
      peers.peer_reports, peers.distinct_documents, peers.sources
    from findings as finding
    join finance.expense_reports as report on report.id = finding.report_id
    left join peers on peers.id = finding.id
  )
  insert into editorial.editorial_reviews (
    target_type, target_id, reviewer_subject, review_type, decision,
    rationale, checklist, reviewed_at
  )
  select
    'analysis.anomaly_finding', classified.id,
    'automated:finance-signal-review/1.0.0', 'data_quality', 'rejected',
    case classified.classification
      when 'same_document' then
        'O mesmo documento oficial foi registrado mais de uma vez pelo processamento da plataforma; não há duplicidade na fonte.'
      when 'portal_tcm_scope' then
        'Portal da Prefeitura (consolidado, inclui a Câmara) e TCM-BA (só o Executivo) publicam o mesmo mês com escopos diferentes, reconciliados no fechamento mensal (ADR 0098).'
      when 'condition_not_met' then
        'A condição da regra não se confirma nos valores atuais do demonstrativo.'
    end,
    jsonb_build_object(
      'classification', classified.classification,
      'peer_reports', classified.peer_reports,
      'distinct_documents', classified.distinct_documents,
      'sources', to_jsonb(classified.sources),
      'layer', 'code',
      'methodology', 'finance-signal-review/1.0.0',
      'adr', '0099'
    ),
    statement_timestamp()
  from classified
  where classified.classification is not null;
  get diagnostics recorded = row_count;
  return recorded;
end;
$function$;

revoke all on function analysis.review_finance_signals() from public, anon, authenticated;

commit;
