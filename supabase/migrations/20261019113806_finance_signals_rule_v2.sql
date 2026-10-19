begin;

-- Regra v2 de períodos duplicados (finance-anomaly-rules/1.1.0) e revisão
-- automatizada ao fim de cada atualização (ADR 0099). A v1 contava linhas de
-- relatório e disparava para o mesmo documento registrado duas vezes ou para
-- portal × TCM-BA do mesmo mês; a v2 só dispara quando a mesma fonte publica
-- documentos distintos com totais diferentes para o mesmo órgão e período.
create or replace function analysis.refresh_finance_signals()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  inserted_count integer := 0;
  current_count integer := 0;
begin
  with sourced_reports as (
    select report.*, origin_endpoint.data_source_id
    from finance.expense_reports as report
    join raw.raw_records as origin on origin.id = report.origin_raw_record_id
    join raw.raw_artifacts as origin_artifact on origin_artifact.id = origin.raw_artifact_id
    join source.source_endpoints as origin_endpoint
      on origin_endpoint.id = origin_artifact.source_endpoint_id
    where report.validation_status = 'validated'
      and report.published_at is not null
  ),
  divergent_periods as (
    select report.public_body_id, report.fiscal_year, report.period_start,
      report.period_end, report.data_source_id,
      count(distinct report.source_document_artifact_id) as period_document_count,
      count(distinct (
        report.total_updated_amount, report.total_committed_to_date_amount,
        report.total_liquidated_to_date_amount, report.total_paid_to_date_amount
      )) as distinct_totals
    from sourced_reports as report
    group by report.public_body_id, report.fiscal_year, report.period_start,
      report.period_end, report.data_source_id
    having count(distinct report.source_document_artifact_id) > 1
      and count(distinct (
        report.total_updated_amount, report.total_committed_to_date_amount,
        report.total_liquidated_to_date_amount, report.total_paid_to_date_amount
      )) > 1
  )
  insert into analysis.anomaly_findings (
    origin_raw_record_id,
    anomaly_rule_id,
    target_type,
    target_id,
    version,
    deterministic_inputs,
    deterministic_output,
    status,
    public_explanation
  )
  select
    report.origin_raw_record_id,
    rule.id,
    'finance.expense_report',
    report.id,
    2,
    jsonb_build_object(
      'public_body_id', report.public_body_id,
      'fiscal_year', report.fiscal_year,
      'period_start', report.period_start,
      'period_end', report.period_end,
      'data_source_id', report.data_source_id
    ),
    jsonb_build_object(
      'period_document_count', period.period_document_count,
      'distinct_totals', period.distinct_totals,
      'source_document_artifact_id', report.source_document_artifact_id
    ),
    'triage',
    'A mesma fonte publicou documentos oficiais diferentes, com totais diferentes, para o mesmo órgão e período. Uma das versões pode ser retificação; a soma exige reconciliação. É um indício que merece apuração, não prova de irregularidade.'
  from sourced_reports as report
  join divergent_periods as period
    on period.public_body_id = report.public_body_id
   and period.fiscal_year = report.fiscal_year
   and period.period_start = report.period_start
   and period.period_end = report.period_end
   and period.data_source_id = report.data_source_id
  join analysis.anomaly_rules as rule
    on rule.slug = 'finance-duplicate-period'
   and rule.version = 2
   and rule.enabled
  where not exists (
    select 1
    from analysis.anomaly_findings as existing
    where existing.anomaly_rule_id = rule.id
      and existing.target_type = 'finance.expense_report'
      and existing.target_id = report.id
      and existing.version = 2
  );
  get diagnostics current_count = row_count;
  inserted_count := inserted_count + current_count;

  insert into analysis.anomaly_findings (
    origin_raw_record_id,
    anomaly_rule_id,
    target_type,
    target_id,
    version,
    deterministic_inputs,
    deterministic_output,
    status,
    public_explanation
  )
  select
    report.origin_raw_record_id,
    rule.id,
    'finance.expense_report',
    report.id,
    1,
    jsonb_build_object(
      'total_committed_to_date_amount', report.total_committed_to_date_amount,
      'total_liquidated_to_date_amount', report.total_liquidated_to_date_amount,
      'total_paid_to_date_amount', report.total_paid_to_date_amount,
      'total_updated_amount', report.total_updated_amount,
      'total_balance_amount', report.total_balance_amount
    ),
    jsonb_build_object(
      'paid_above_committed', report.total_paid_to_date_amount > report.total_committed_to_date_amount,
      'liquidated_above_committed', report.total_liquidated_to_date_amount > report.total_committed_to_date_amount,
      'negative_total', (
        report.total_updated_amount < 0
        or report.total_committed_period_amount < 0
        or report.total_committed_to_date_amount < 0
        or report.total_liquidated_period_amount < 0
        or report.total_liquidated_to_date_amount < 0
        or report.total_paid_period_amount < 0
        or report.total_paid_to_date_amount < 0
        or report.total_balance_amount < 0
      )
    ),
    'triage',
    'Os totais informados no demonstrativo precisam de conferência na relação entre empenho, liquidação e pagamento ou contêm valor negativo. O sinal pede verificação da fonte e do período; não é prova de irregularidade.'
  from finance.expense_reports as report
  join analysis.anomaly_rules as rule
    on rule.slug = 'finance-accounting-consistency'
   and rule.version = 1
   and rule.enabled
  where report.validation_status = 'validated'
    and report.published_at is not null
    and (
      report.total_paid_to_date_amount > report.total_committed_to_date_amount
      or report.total_liquidated_to_date_amount > report.total_committed_to_date_amount
      or report.total_updated_amount < 0
      or report.total_committed_period_amount < 0
      or report.total_committed_to_date_amount < 0
      or report.total_liquidated_period_amount < 0
      or report.total_liquidated_to_date_amount < 0
      or report.total_paid_period_amount < 0
      or report.total_paid_to_date_amount < 0
      or report.total_balance_amount < 0
    )
    and not exists (
      select 1
      from analysis.anomaly_findings as existing
      where existing.anomaly_rule_id = rule.id
        and existing.target_type = 'finance.expense_report'
        and existing.target_id = report.id
        and existing.version = 1
    );
  get diagnostics current_count = row_count;
  inserted_count := inserted_count + current_count;

  -- Cada sinal recebe uma evidência de cálculo vinculada ao registro bruto.
  -- O teste de existência torna a operação idempotente.
  insert into evidence.evidence_items (
    target_type,
    target_id,
    raw_artifact_id,
    raw_record_id,
    evidence_kind,
    source_url,
    excerpt,
    locator,
    content_sha256,
    parser_version,
    is_primary
  )
  select
    'analysis.anomaly_finding',
    finding.id,
    origin.raw_artifact_id,
    origin.id,
    'calculation',
    case when artifact.source_url like 'https://%' then artifact.source_url else null end,
    'Sinal calculado por regra determinística; consulte o documento oficial e o período antes de interpretar.',
    jsonb_build_object('rule_id', finding.anomaly_rule_id, 'methodology', 'finance-anomaly-rules/1.1.0'),
    artifact.sha256,
    'finance-anomaly-rules/1.1.0',
    true
  from analysis.anomaly_findings as finding
  join raw.raw_records as origin on origin.id = finding.origin_raw_record_id
  join raw.raw_artifacts as artifact on artifact.id = origin.raw_artifact_id
  where finding.target_type = 'finance.expense_report'
    and not exists (
      select 1
      from evidence.evidence_items as existing
      where existing.target_type = 'analysis.anomaly_finding'
        and existing.target_id = finding.id
        and existing.evidence_kind = 'calculation'
    );

  -- Primeira camada da revisão automatizada (ADR 0099): rejeita com motivo o
  -- que tem explicação verificável; o resto aguarda a conferência do agente.
  perform analysis.review_finance_signals();

  return inserted_count;
end;
$function$;

commit;
