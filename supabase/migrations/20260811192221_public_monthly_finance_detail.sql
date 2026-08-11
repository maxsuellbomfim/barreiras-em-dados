begin;

drop function if exists api.get_public_monthly_finance_detail(date);

create function api.get_public_monthly_finance_detail(
  period_filter date
)
returns table (
  closure_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_amount numeric,
  revenue_report_count integer,
  revenue_line_count integer,
  expense_paid_amount numeric,
  expense_committed_amount numeric,
  expense_liquidated_amount numeric,
  expense_report_count integer,
  operational_difference_amount numeric,
  closure_status text,
  coverage_note text,
  calculation_methodology text,
  revenue_documents jsonb,
  expense_documents jsonb,
  evidence_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if period_filter is null then
    raise exception 'period_filter e obrigatorio'
      using errcode = '22004';
  end if;

  if period_filter <> date_trunc('month', period_filter)::date then
    raise exception 'period_filter deve ser o primeiro dia do mes'
      using errcode = '22023';
  end if;

  if extract(year from period_filter) < 1900
     or extract(year from period_filter) > 2200 then
    raise exception 'period_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with closure as materialized (
    select calculated.*
    from api.get_public_monthly_finance_closures_calculated(
      120,
      extract(year from period_filter)::smallint
    ) as calculated
    where calculated.period_start = period_filter
  ),
  revenue_current as materialized (
    select versioned.*
    from (
      select
        revenue.*,
        row_number() over (
          partition by revenue.public_body_id,
            coalesce(revenue.external_id, revenue.id::text)
          order by revenue.version desc, revenue.created_at desc,
            revenue.id desc
        ) as current_row
      from finance.revenues as revenue
      where revenue.validation_status = 'validated'
        and revenue.published_at is not null
        and revenue.revenue_date is not null
        and revenue.source_document_artifact_id is not null
        and date_trunc('month', revenue.revenue_date)::date = period_filter
        and finance.has_exact_document_lineage(
          revenue.origin_raw_record_id,
          revenue.source_document_artifact_id
        )
    ) as versioned
    where versioned.current_row = 1
  ),
  revenue_document_rows as materialized (
    select
      revenue.public_body_id,
      revenue.source_document_artifact_id,
      document.source_url as document_url,
      document.sha256 as artifact_sha256,
      source_artifact.source_url,
      source_artifact.sha256 as source_artifact_sha256,
      count(*)::integer as line_count,
      max(revenue.report_total_period_amount) as report_amount
    from revenue_current as revenue
    join raw.raw_records as origin
      on origin.id = revenue.origin_raw_record_id
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = revenue.source_document_artifact_id
    group by revenue.public_body_id,
      revenue.source_document_artifact_id,
      document.source_url,
      document.sha256,
      source_artifact.source_url,
      source_artifact.sha256
  ),
  revenue_evidence as materialized (
    select
      rows.public_body_id,
      jsonb_agg(
        jsonb_build_object(
          'document_url', rows.document_url,
          'artifact_sha256', rows.artifact_sha256,
          'source_url', rows.source_url,
          'source_artifact_sha256', rows.source_artifact_sha256,
          'line_count', rows.line_count,
          'report_amount', rows.report_amount::text
        )
        order by rows.artifact_sha256
      ) as documents
    from revenue_document_rows as rows
    group by rows.public_body_id
  ),
  expense_current as materialized (
    select ranked.*
    from (
      select
        report.*,
        row_number() over (
          partition by report.source_document_artifact_id
          order by report.version desc, report.created_at desc,
            report.id desc
        ) as current_row
      from finance.expense_reports as report
      where report.validation_status = 'validated'
        and report.published_at is not null
        and report.source_document_artifact_id is not null
        and date_trunc('month', report.period_end)::date = period_filter
        and finance.has_exact_document_lineage(
          report.origin_raw_record_id,
          report.source_document_artifact_id
        )
    ) as ranked
    where ranked.current_row = 1
  ),
  expense_evidence as materialized (
    select
      report.public_body_id,
      jsonb_agg(
        jsonb_build_object(
          'document_url', document.source_url,
          'artifact_sha256', document.sha256,
          'source_url', source_artifact.source_url,
          'source_artifact_sha256', source_artifact.sha256,
          'committed_amount', report.total_committed_period_amount::text,
          'liquidated_amount', report.total_liquidated_period_amount::text,
          'paid_amount', report.total_paid_period_amount::text
        )
        order by document.sha256
      ) as documents
    from expense_current as report
    join raw.raw_records as origin
      on origin.id = report.origin_raw_record_id
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = report.source_document_artifact_id
    group by report.public_body_id
  )
  select
    closure.closure_id,
    closure.fiscal_year,
    closure.period_start,
    closure.period_end,
    closure.public_body_name,
    closure.revenue_report_amount,
    closure.revenue_report_count,
    closure.revenue_line_count,
    closure.expense_paid_amount,
    closure.expense_committed_amount,
    closure.expense_liquidated_amount,
    closure.expense_report_count,
    closure.operational_difference_amount,
    closure.closure_status,
    closure.coverage_note,
    closure.calculation_methodology,
    coalesce(revenue.documents, '[]'::jsonb),
    coalesce(expense.documents, '[]'::jsonb),
    'public-monthly-finance-detail/1.0.0'::text
  from closure
  left join revenue_evidence as revenue
    on closure.closure_id = revenue.public_body_id::text
      || ':' || period_filter::text
  left join expense_evidence as expense
    on closure.closure_id = expense.public_body_id::text
      || ':' || period_filter::text;
end;
$function$;

revoke all on function api.get_public_monthly_finance_detail(date)
  from public;
grant execute on function api.get_public_monthly_finance_detail(date)
  to anon, authenticated;

comment on function api.get_public_monthly_finance_detail(date) is
  'Detalhe mensal publico com fechamento deterministico e documentos oficiais de receita e despesa.';

commit;
