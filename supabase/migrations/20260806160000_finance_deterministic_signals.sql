-- Primeiras regras determinísticas de qualidade e consistência financeira.
-- Um finding é um sinal revisável, nunca uma conclusão de irregularidade.

insert into analysis.anomaly_rules (
  slug,
  version,
  name,
  description,
  deterministic_spec,
  implementation_version,
  severity,
  enabled
)
values
  (
    'finance-duplicate-period',
    1,
    'Mais de um relatório validado para o mesmo período',
    'Identifica relatórios de despesa validados do mesmo órgão, ano e período. O sinal evita dupla contagem e pede reconciliação documental.',
    jsonb_build_object(
      'source_table', 'finance.expense_reports',
      'filters', jsonb_build_array('validation_status = validated', 'published_at is not null'),
      'group_by', jsonb_build_array('public_body_id', 'fiscal_year', 'period_start', 'period_end'),
      'condition', 'count(*) > 1'
    ),
    'finance-anomaly-rules/1.0.0',
    'low',
    true
  ),
  (
    'finance-accounting-consistency',
    1,
    'Relação contábil que precisa de conferência',
    'Identifica relações atípicas entre empenho, liquidação e pagamento ou valores negativos no demonstrativo publicado.',
    jsonb_build_object(
      'source_table', 'finance.expense_reports',
      'filters', jsonb_build_array('validation_status = validated', 'published_at is not null'),
      'conditions', jsonb_build_array(
        'total_paid_to_date_amount > total_committed_to_date_amount',
        'total_liquidated_to_date_amount > total_committed_to_date_amount',
        'qualquer total financeiro < 0'
      )
    ),
    'finance-anomaly-rules/1.0.0',
    'medium',
    true
  )
on conflict (slug, version) do nothing;

create unique index if not exists anomaly_findings_rule_target_version_idx
  on analysis.anomaly_findings (anomaly_rule_id, target_type, target_id, version);

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
  with current_reports as (
    select
      report.*,
      count(*) over (
        partition by report.public_body_id, report.fiscal_year,
          report.period_start, report.period_end
      ) as period_report_count
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
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
    1,
    jsonb_build_object(
      'public_body_id', report.public_body_id,
      'fiscal_year', report.fiscal_year,
      'period_start', report.period_start,
      'period_end', report.period_end
    ),
    jsonb_build_object(
      'period_report_count', report.period_report_count,
      'source_document_artifact_id', report.source_document_artifact_id
    ),
    'triage',
    'Há mais de um relatório validado para o mesmo órgão e período. O sinal indica que os documentos precisam ser reconciliados antes de qualquer soma; não é prova de irregularidade.'
  from current_reports as report
  join analysis.anomaly_rules as rule
    on rule.slug = 'finance-duplicate-period'
   and rule.version = 1
   and rule.enabled
  where report.period_report_count > 1
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
    jsonb_build_object('rule_id', finding.anomaly_rule_id, 'methodology', 'finance-anomaly-rules/1.0.0'),
    artifact.sha256,
    'finance-anomaly-rules/1.0.0',
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

  return inserted_count;
end;
$function$;

revoke all on function analysis.refresh_finance_signals() from public;
grant usage on schema analysis to collector_worker;
grant execute on function analysis.refresh_finance_signals() to collector_worker;

drop function if exists api.get_public_finance_signals(integer);

create function api.get_public_finance_signals(page_size integer default 50)
returns table (
  finding_id uuid,
  rule_slug text,
  rule_name text,
  severity text,
  target_type text,
  target_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  public_explanation text,
  deterministic_output jsonb,
  source_url text,
  artifact_sha256 text,
  created_at timestamptz
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  select
    finding.id,
    rule.slug,
    rule.name,
    rule.severity,
    finding.target_type,
    finding.target_id,
    report.fiscal_year,
    report.period_start,
    report.period_end,
    body.name,
    finding.public_explanation,
    finding.deterministic_output,
    evidence.source_url,
    artifact.sha256,
    finding.created_at
  from analysis.anomaly_findings as finding
  join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
  join finance.expense_reports as report
    on finding.target_type = 'finance.expense_report'
   and report.id = finding.target_id
  join org.public_bodies as body on body.id = report.public_body_id
  left join lateral (
    select item.source_url
    from evidence.evidence_items as item
    where item.target_type = 'analysis.anomaly_finding'
      and item.target_id = finding.id
      and item.is_primary
    order by item.created_at desc
    limit 1
  ) as evidence on true
  join raw.raw_records as origin on origin.id = finding.origin_raw_record_id
  join raw.raw_artifacts as artifact on artifact.id = origin.raw_artifact_id
  where finding.status in ('triage', 'needs_context', 'confirmed_as_signal')
    and finding.supersedes_id is null
  order by report.period_end desc, finding.created_at desc, finding.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_finance_signals(integer) from public;
grant execute on function api.get_public_finance_signals(integer) to anon, authenticated;

comment on function analysis.refresh_finance_signals() is
  'Atualiza sinais financeiros determinísticos e suas evidências. Um sinal não é prova de irregularidade.';
comment on function api.get_public_finance_signals(integer) is
  'Projeção pública de sinais financeiros revisáveis, com fonte e explicação neutra.';
