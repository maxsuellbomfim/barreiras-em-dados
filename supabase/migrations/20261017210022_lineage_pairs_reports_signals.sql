begin;

-- Sinais financeiros, relatórios de despesa e conflitos de fonte chamavam
-- finance.has_exact_document_lineage linha a linha (2,0 s, 0,8 s e 0,5 s com
-- cache quente em 17/10/2026; a sonda horária de disponibilidade regenera as
-- páginas e estourava os 3 s do papel anônimo). Passam a usar a projeção
-- set-based de linhagem, a mesma das funções agregadas e do detalhe mensal.
-- Mesmo resultado e mesmas metodologias.

create or replace function api.get_public_finance_signals(
  page_size integer default 50
)
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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  )
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
  join exact_lineage as lineage
    on lineage.origin_raw_record_id = report.origin_raw_record_id
   and lineage.document_artifact_id = report.source_document_artifact_id
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
    and finding.origin_raw_record_id = report.origin_raw_record_id
  order by report.period_end desc, finding.created_at desc, finding.id desc
  limit page_size;
end;
$function$;

create or replace function api.get_public_expense_reports(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  expense_report_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  total_updated_amount numeric,
  total_committed_period_amount numeric,
  total_committed_to_date_amount numeric,
  total_liquidated_period_amount numeric,
  total_liquidated_to_date_amount numeric,
  total_paid_period_amount numeric,
  total_paid_to_date_amount numeric,
  total_unpaid_committed_amount numeric,
  total_balance_amount numeric,
  currency text,
  public_body_name text,
  source_url text,
  document_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text,
  validation_status text
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

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  ranked as (
    select
      report.*,
      row_number() over (
        partition by report.source_document_artifact_id
        order by report.version desc, report.created_at desc, report.id desc
      ) as current_row
    from finance.expense_reports as report
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.document_artifact_id = report.source_document_artifact_id
    where report.validation_status = 'validated'
      and report.published_at is not null
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
  )
  select
    report.id,
    report.fiscal_year,
    report.period_start,
    report.period_end,
    report.total_updated_amount,
    report.total_committed_period_amount,
    report.total_committed_to_date_amount,
    report.total_liquidated_period_amount,
    report.total_liquidated_to_date_amount,
    report.total_paid_period_amount,
    report.total_paid_to_date_amount,
    report.total_unpaid_committed_amount,
    report.total_balance_amount,
    report.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    'public-expense-reports/1.1.0',
    report.validation_status
  from ranked as report
  join org.public_bodies as body
    on body.id = report.public_body_id
  join raw.raw_records as origin
    on origin.id = report.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = report.source_document_artifact_id
  where report.current_row = 1
  order by report.period_end desc, report.created_at desc, report.id desc
  limit page_size;
end;
$function$;

create or replace function api.get_public_expense_report_source_conflicts(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  expense_report_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  conflict_scope text,
  field_name text,
  budget_unit_code text,
  budget_unit_name text,
  declared_amount numeric,
  calculated_amount numeric,
  difference_amount numeric,
  document_source_url text,
  document_artifact_sha256 text,
  methodology_version text
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
  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  ranked_reports as materialized (
    select
      report.*,
      row_number() over (
        partition by report.source_document_artifact_id
        order by report.version desc, report.created_at desc, report.id desc
      ) as current_row
    from finance.expense_reports as report
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.document_artifact_id = report.source_document_artifact_id
    where report.validation_status = 'validated'
      and report.published_at is not null
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
  ), parsed as (
    select
      report.id as expense_report_id,
      report.fiscal_year,
      report.period_start,
      report.period_end,
      coalesce(
        nullif(conflict.first_value ->> 'scope', ''),
        'report_total'
      ) as conflict_scope,
      coalesce(
        nullif(conflict.first_value ->> 'field_name', ''),
        conflict.field_name
      ) as public_field_name,
      nullif(conflict.first_value ->> 'budget_unit_code', '')
        as budget_unit_code,
      nullif(conflict.first_value ->> 'budget_unit_name', '')
        as budget_unit_name,
      case
        when conflict.first_value ->> 'declared_amount'
          ~ '^-?[0-9]+([.][0-9]{1,2})?$'
        then (conflict.first_value ->> 'declared_amount')::numeric
      end as declared_amount,
      case
        when conflict.second_value ->> 'calculated_amount'
          ~ '^-?[0-9]+([.][0-9]{1,2})?$'
        then (conflict.second_value ->> 'calculated_amount')::numeric
      end as calculated_amount,
      case
        when conflict.second_value ->> 'difference_amount'
          ~ '^-?[0-9]+([.][0-9]{1,2})?$'
        then (conflict.second_value ->> 'difference_amount')::numeric
      end as difference_amount,
      document.source_url as document_source_url,
      document.sha256 as document_artifact_sha256,
      conflict.created_at,
      conflict.id
    from ranked_reports as report
    join evidence.source_conflicts as conflict
      on conflict.target_type = 'finance.expense_reports'
     and conflict.target_id = report.id
     and conflict.status in ('open', 'accepted_difference')
    join raw.raw_artifacts as document
      on document.id = report.source_document_artifact_id
     and document.artifact_kind = 'document'
    where report.current_row = 1
  )
  select
    parsed.expense_report_id,
    parsed.fiscal_year,
    parsed.period_start,
    parsed.period_end,
    parsed.conflict_scope,
    parsed.public_field_name,
    parsed.budget_unit_code,
    parsed.budget_unit_name,
    parsed.declared_amount,
    parsed.calculated_amount,
    parsed.difference_amount,
    parsed.document_source_url,
    parsed.document_artifact_sha256,
    'public-expense-source-conflicts/1.1.0'::text
  from parsed
  where parsed.conflict_scope in ('report_total', 'budget_unit_subtotal')
    and parsed.public_field_name ~ '^(total_)?[a-z_]+_amount$'
    and parsed.declared_amount is not null
    and parsed.calculated_amount is not null
    and parsed.difference_amount is not null
    and parsed.document_source_url like 'https://%'
    and parsed.document_artifact_sha256 ~ '^[0-9a-f]{64}$'
    and (
      parsed.conflict_scope = 'report_total'
      or (
        parsed.budget_unit_code ~ '^[0-9]{6,8}$'
        and parsed.budget_unit_name is not null
      )
    )
  order by parsed.period_end desc, parsed.conflict_scope,
    parsed.public_field_name, parsed.created_at desc, parsed.id desc
  limit page_size;
end;
$function$;

notify pgrst, 'reload schema';

commit;
