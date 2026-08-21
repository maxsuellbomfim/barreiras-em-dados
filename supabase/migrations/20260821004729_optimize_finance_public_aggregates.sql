begin;

create or replace function finance.get_exact_document_lineage_pairs()
returns table (
  origin_raw_record_id uuid,
  document_artifact_id uuid
)
language sql
stable
security definer
set search_path = ''
as $function$
  with direct_lineage as materialized (
    select
      origin.id as origin_raw_record_id,
      document.id as document_artifact_id
    from raw.raw_records as origin
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.parent_artifact_id = source_artifact.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url = origin.payload ->> 'url'
    where origin.source_record_key is not null
  ),
  current_corrections as (
    select distinct on (
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id
    )
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id,
      lineage.effective_raw_record_id
    from finance.document_lineage_versions as lineage
    where lineage.lineage_status = 'corrected'
    order by
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id,
      lineage.version desc,
      lineage.created_at desc,
      lineage.id desc
  ),
  corrected_lineage as (
    select
      correction.normalized_origin_raw_record_id as origin_raw_record_id,
      correction.document_artifact_id
    from current_corrections as correction
    join direct_lineage as direct
      on direct.origin_raw_record_id = correction.effective_raw_record_id
     and direct.document_artifact_id = correction.document_artifact_id
  )
  select direct.origin_raw_record_id, direct.document_artifact_id
  from direct_lineage as direct
  union
  select corrected.origin_raw_record_id, corrected.document_artifact_id
  from corrected_lineage as corrected;
$function$;

revoke all on function finance.get_exact_document_lineage_pairs()
  from public, anon, authenticated;

comment on function finance.get_exact_document_lineage_pairs() is
  'Pares de origem e PDF com linhagem direta ou corrigida, calculados em conjunto para agregações internas.';

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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
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
      join exact_lineage as lineage
        on lineage.origin_raw_record_id = revenue.origin_raw_record_id
       and lineage.document_artifact_id = revenue.source_document_artifact_id
      where revenue.validation_status = 'validated'
        and revenue.published_at is not null
        and revenue.revenue_date is not null
        and revenue.source_document_artifact_id is not null
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
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.document_artifact_id = report.source_document_artifact_id
    where report.validation_status = 'validated'
      and report.published_at is not null
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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  bodies as (
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
      join exact_lineage as lineage
        on lineage.origin_raw_record_id = revenue.origin_raw_record_id
       and lineage.document_artifact_id = revenue.source_document_artifact_id
      where revenue.validation_status = 'validated'
        and revenue.published_at is not null
        and revenue.revenue_date is not null
        and revenue.source_document_artifact_id is not null
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
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.document_artifact_id = report.source_document_artifact_id
    where report.validation_status = 'validated'
      and report.published_at is not null
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

comment on function api.get_public_monthly_finance_closures_calculated(integer, smallint) is
  'Fechamento mensal determinístico com validação de linhagem calculada em conjunto.';

comment on function api.get_public_finance_coverage_calculated(integer, smallint, smallint) is
  'Cobertura mensal determinística com validação de linhagem calculada em conjunto.';

commit;
