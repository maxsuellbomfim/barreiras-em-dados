-- Projeção pública da cobertura mensal esperada.
-- Ausência de registro é mostrada como falta de cobertura, nunca como valor zero.

drop function if exists api.get_public_finance_coverage(integer, smallint, smallint);

create function api.get_public_finance_coverage(
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
  revenue_months as (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      count(distinct revenue.source_document_artifact_id)::integer as report_count
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and revenue.revenue_date is not null
      and revenue.source_document_artifact_id is not null
      and extract(year from revenue.revenue_date)::smallint between fiscal_year_from and effective_year_to
    group by revenue.public_body_id, date_trunc('month', revenue.revenue_date)::date
  ),
  expense_months as (
    select
      report.public_body_id,
      date_trunc('month', report.period_end)::date as period_start,
      count(distinct report.source_document_artifact_id)::integer as report_count
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and extract(year from report.period_end)::smallint between fiscal_year_from and effective_year_to
    group by report.public_body_id, date_trunc('month', report.period_end)::date
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
    'finance-coverage/1.0.0'::text
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

revoke all on function api.get_public_finance_coverage(integer, smallint, smallint)
  from public;
grant execute on function api.get_public_finance_coverage(integer, smallint, smallint)
  to anon, authenticated;

comment on function api.get_public_finance_coverage(integer, smallint, smallint) is
  'Cobertura mensal esperada de receitas e despesas validadas; ausência nunca é tratada como zero.';
