begin;

-- A resposta da API municipal agrega diversos meses em um artefato bruto.
-- Um PDF somente sustenta um valor normalizado quando o identificador do
-- registro que originou o download coincide exatamente com o metadado do PDF.
create or replace function finance.has_exact_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from raw.raw_records as origin
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = document_artifact_id
     and document.parent_artifact_id = source_artifact.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
    where origin.id = origin_record_id
      and origin.source_record_key is not null
  );
$function$;

revoke all on function finance.has_exact_document_lineage(uuid, uuid)
  from public, anon, authenticated;

comment on function finance.has_exact_document_lineage(uuid, uuid) is
  'Confirma que o PDF financeiro pertence ao registro bruto exato que sustenta o valor normalizado.';

create or replace function api.get_public_revenues(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  revenue_id uuid,
  external_id text,
  fiscal_year smallint,
  revenue_date date,
  revenue_code text,
  description text,
  collected_amount numeric,
  accumulated_amount numeric,
  report_total_period_amount numeric,
  collection_direction text,
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
  with ranked as (
    select
      revenue.*,
      row_number() over (
        partition by revenue.public_body_id,
          coalesce(revenue.external_id, revenue.id::text)
        order by revenue.version desc, revenue.created_at desc, revenue.id desc
      ) as current_row
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and finance.has_exact_document_lineage(
        revenue.origin_raw_record_id,
        revenue.source_document_artifact_id
      )
      and (
        fiscal_year_filter is null
        or revenue.fiscal_year = fiscal_year_filter
      )
  )
  select
    revenue.id,
    revenue.external_id,
    revenue.fiscal_year,
    revenue.revenue_date,
    revenue.revenue_code,
    revenue.description,
    coalesce(
      revenue.collected_amount_signed,
      case
        when revenue.collection_direction in ('deduction', 'adjustment')
        then -revenue.collected_amount
        else revenue.collected_amount
      end
    ),
    coalesce(
      revenue.accumulated_amount_signed,
      case
        when revenue.collection_direction in ('deduction', 'adjustment')
        then -revenue.accumulated_amount
        else revenue.accumulated_amount
      end
    ),
    revenue.report_total_period_amount,
    revenue.collection_direction,
    revenue.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    'public-revenues/1.3.0',
    revenue.validation_status
  from ranked as revenue
  join org.public_bodies as body
    on body.id = revenue.public_body_id
  join raw.raw_records as origin
    on origin.id = revenue.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = revenue.source_document_artifact_id
  where revenue.current_row = 1
  order by revenue.revenue_date desc nulls last, revenue.created_at desc,
    revenue.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_revenues(integer, smallint) from public;
grant execute on function api.get_public_revenues(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_revenues(integer, smallint) is
  'Receitas validadas com sinal contábil e vínculo exato entre registro bruto e PDF.';

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
  with ranked as (
    select
      report.*,
      row_number() over (
        partition by report.source_document_artifact_id
        order by report.version desc, report.created_at desc, report.id desc
      ) as current_row
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and finance.has_exact_document_lineage(
        report.origin_raw_record_id,
        report.source_document_artifact_id
      )
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

revoke all on function api.get_public_expense_reports(integer, smallint)
  from public;
grant execute on function api.get_public_expense_reports(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_expense_reports(integer, smallint) is
  'Relatórios de despesa validados com vínculo exato entre registro bruto e PDF.';

create or replace function api.get_public_expense_lines(
  report_filter uuid default null,
  page_size integer default 50,
  page_offset integer default 0
)
returns table (
  expense_line_id uuid,
  expense_report_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  line_number integer,
  expense_code text,
  description text,
  source_code text,
  fixed_amount numeric,
  additions_amount numeric,
  reductions_amount numeric,
  updated_amount numeric,
  committed_period_amount numeric,
  committed_to_date_amount numeric,
  liquidated_period_amount numeric,
  liquidated_to_date_amount numeric,
  paid_period_amount numeric,
  paid_to_date_amount numeric,
  unpaid_committed_amount numeric,
  balance_amount numeric,
  currency text,
  source_url text,
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
  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with current_reports as (
    select
      report.*,
      row_number() over (
        partition by report.source_document_artifact_id
        order by report.version desc, report.created_at desc, report.id desc
      ) as current_row
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and finance.has_exact_document_lineage(
        report.origin_raw_record_id,
        report.source_document_artifact_id
      )
  )
  select
    line.id,
    report.id,
    report.fiscal_year,
    report.period_start,
    report.period_end,
    line.line_number,
    line.expense_code,
    line.description,
    line.source_code,
    line.fixed_amount,
    line.additions_amount,
    line.reductions_amount,
    line.updated_amount,
    line.committed_period_amount,
    line.committed_to_date_amount,
    line.liquidated_period_amount,
    line.liquidated_to_date_amount,
    line.paid_period_amount,
    line.paid_to_date_amount,
    line.unpaid_committed_amount,
    line.balance_amount,
    line.currency::text,
    source_artifact.source_url,
    document.source_url,
    document.sha256,
    'public-expense-lines/1.1.0'
  from finance.expense_lines as line
  join current_reports as report
    on report.id = line.report_id
   and report.current_row = 1
  join raw.raw_records as origin
    on origin.id = report.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = report.source_document_artifact_id
  where line.origin_raw_record_id = report.origin_raw_record_id
    and (report_filter is null or report.id = report_filter)
  order by line.paid_period_amount desc, line.line_number asc
  limit page_size
  offset page_offset;
end;
$function$;

revoke all on function api.get_public_expense_lines(uuid, integer, integer)
  from public;
grant execute on function api.get_public_expense_lines(uuid, integer, integer)
  to anon, authenticated;

comment on function api.get_public_expense_lines(uuid, integer, integer) is
  'Linhas de despesa do relatório vigente com origem bruta e PDF exatos.';

create or replace function api.get_public_monthly_finance_closures_calculated(
  page_size integer default 24,
  fiscal_year_filter smallint default null
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
  calculation_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if page_size < 1 or page_size > 120 then
    raise exception 'page_size deve estar entre 1 e 120'
      using errcode = '22023';
  end if;

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with revenue_current as (
    select *
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
        and finance.has_exact_document_lineage(
          revenue.origin_raw_record_id,
          revenue.source_document_artifact_id
        )
        and (
          fiscal_year_filter is null
          or revenue.fiscal_year = fiscal_year_filter
        )
    ) as versioned_revenue
    where versioned_revenue.current_row = 1
  ),
  revenue_source_reports as (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      revenue.source_document_artifact_id,
      max(revenue.report_total_period_amount) as report_amount,
      count(*)::integer as line_count
    from revenue_current as revenue
    group by
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date,
      revenue.source_document_artifact_id
  ),
  revenue_months as (
    select
      source.public_body_id,
      source.period_start,
      sum(source.report_amount) as report_amount,
      count(*)::integer as report_count,
      sum(source.line_count)::integer as line_count
    from revenue_source_reports as source
    group by source.public_body_id, source.period_start
  ),
  expense_current as (
    select distinct on (
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id
    )
      report.*
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and finance.has_exact_document_lineage(
        report.origin_raw_record_id,
        report.source_document_artifact_id
      )
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
    order by
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id,
      report.version desc,
      report.created_at desc,
      report.id desc
  ),
  expense_months as (
    select
      expense.public_body_id,
      date_trunc('month', expense.period_end)::date as period_start,
      max(expense.period_end)::date as period_end,
      max(expense.total_paid_period_amount) as paid_amount,
      max(expense.total_committed_period_amount) as committed_amount,
      max(expense.total_liquidated_period_amount) as liquidated_amount,
      count(*)::integer as report_count
    from expense_current as expense
    group by expense.public_body_id, date_trunc('month', expense.period_end)::date
  ),
  periods as (
    select public_body_id, period_start from revenue_months
    union
    select public_body_id, period_start from expense_months
  )
  select
    periods.public_body_id::text || ':' || periods.period_start::text,
    extract(year from periods.period_start)::smallint,
    periods.period_start,
    (periods.period_start + interval '1 month - 1 day')::date,
    body.name,
    revenue.report_amount,
    coalesce(revenue.report_count, 0),
    coalesce(revenue.line_count, 0),
    expense.paid_amount,
    expense.committed_amount,
    expense.liquidated_amount,
    coalesce(expense.report_count, 0),
    case
      when revenue.report_count = 1 and expense.report_count = 1
        then revenue.report_amount - expense.paid_amount
      else null
    end,
    case
      when revenue.report_count is null or expense.report_count is null
        then 'needs_data'::text
      when revenue.report_count > 1 or expense.report_count > 1
        then 'needs_review'::text
      else 'operational'::text
    end,
    case
      when revenue.report_count is null
        then 'Há pagamentos publicados, mas ainda não há relatório de receita comparável.'
      when expense.report_count is null
        then 'Há receita publicada, mas ainda não há relatório de pagamentos comparável.'
      when revenue.report_count > 1 or expense.report_count > 1
        then 'Há mais de um relatório na mesma competência; o total aguarda reconciliação para evitar dupla contagem.'
      else 'Diferença entre a receita total declarada no relatório e o pagamento efetivado no mês. Não é superávit fiscal.'
    end,
    'monthly-finance-closure/1.1.0'::text
  from periods
  join org.public_bodies as body on body.id = periods.public_body_id
  left join revenue_months as revenue
    on revenue.public_body_id = periods.public_body_id
   and revenue.period_start = periods.period_start
  left join expense_months as expense
    on expense.public_body_id = periods.public_body_id
   and expense.period_start = periods.period_start
  order by periods.period_start desc, body.name
  limit page_size;
end;
$function$;

create or replace function api.get_public_finance_coverage_calculated(
  page_size integer default 120,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  coverage_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_count integer,
  expense_report_count integer,
  coverage_status text,
  coverage_note text,
  calculation_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if page_size < 1 or page_size > 240 then
    raise exception 'page_size deve estar entre 1 e 240'
      using errcode = '22023';
  end if;

  if fiscal_year_from < 1900 or fiscal_year_from > effective_year_to
     or effective_year_to > 2200 then
    raise exception 'intervalo fiscal inválido'
      using errcode = '22023';
  end if;

  return query
  with bodies as (
    select distinct on (body.id)
      body.id,
      body.name
    from org.public_bodies as body
    where body.body_type = 'executive'
    order by body.id, body.version desc, body.created_at desc
  ),
  months as (
    select generate_series(
      make_date(fiscal_year_from, 1, 1),
      least(
        make_date(effective_year_to, 12, 1),
        date_trunc('month', current_date)::date
      ),
      interval '1 month'
    )::date as period_start
  ),
  revenue_current as (
    select *
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
        and finance.has_exact_document_lineage(
          revenue.origin_raw_record_id,
          revenue.source_document_artifact_id
        )
        and extract(year from revenue.revenue_date)::smallint
          between fiscal_year_from and effective_year_to
    ) as versioned_revenue
    where versioned_revenue.current_row = 1
  ),
  revenue_months as (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      count(distinct revenue.source_document_artifact_id)::integer
        as report_count
    from revenue_current as revenue
    group by revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date
  ),
  expense_current as (
    select distinct on (report.source_document_artifact_id)
      report.*
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and finance.has_exact_document_lineage(
        report.origin_raw_record_id,
        report.source_document_artifact_id
      )
      and extract(year from report.period_end)::smallint
        between fiscal_year_from and effective_year_to
    order by report.source_document_artifact_id, report.version desc,
      report.created_at desc, report.id desc
  ),
  expense_months as (
    select
      report.public_body_id,
      date_trunc('month', report.period_end)::date as period_start,
      count(distinct report.source_document_artifact_id)::integer
        as report_count
    from expense_current as report
    group by report.public_body_id,
      date_trunc('month', report.period_end)::date
  )
  select
    body.id::text || ':' || months.period_start::text,
    extract(year from months.period_start)::smallint,
    months.period_start,
    (months.period_start + interval '1 month - 1 day')::date,
    body.name,
    coalesce(revenue.report_count, 0),
    coalesce(expense.report_count, 0),
    case
      when coalesce(revenue.report_count, 0) > 1
        or coalesce(expense.report_count, 0) > 1
        then 'needs_review'::text
      when revenue.report_count is not null and expense.report_count is not null
        then 'complete'::text
      when revenue.report_count is not null
        then 'revenue_only'::text
      when expense.report_count is not null
        then 'expense_only'::text
      else 'missing'::text
    end,
    case
      when coalesce(revenue.report_count, 0) > 1
        or coalesce(expense.report_count, 0) > 1
        then 'Há mais de um relatório na competência; a leitura aguarda reconciliação para evitar dupla contagem.'
      when revenue.report_count is not null and expense.report_count is not null
        then 'Há pelo menos um relatório validado de receita e um de despesa para este mês.'
      when revenue.report_count is not null
        then 'Há receita validada, mas ainda não há relatório de despesa comparável.'
      when expense.report_count is not null
        then 'Há despesa validada, mas ainda não há relatório de receita comparável.'
      else 'Nenhum relatório financeiro validado foi publicado para este mês; isso não significa receita ou despesa zero.'
    end,
    'finance-coverage/1.1.0'::text
  from bodies as body
  cross join months
  left join revenue_months as revenue
    on revenue.public_body_id = body.id
   and revenue.period_start = months.period_start
  left join expense_months as expense
    on expense.public_body_id = body.id
   and expense.period_start = months.period_start
  order by months.period_start desc, body.name
  limit page_size;
end;
$function$;

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
    and finding.origin_raw_record_id = report.origin_raw_record_id
    and finance.has_exact_document_lineage(
      report.origin_raw_record_id,
      report.source_document_artifact_id
    )
  order by report.period_end desc, finding.created_at desc, finding.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_finance_signals(integer) from public;
grant execute on function api.get_public_finance_signals(integer)
  to anon, authenticated;

comment on function api.get_public_finance_signals(integer) is
  'Sinais financeiros revisáveis cuja origem bruta coincide com o PDF analisado.';

commit;
