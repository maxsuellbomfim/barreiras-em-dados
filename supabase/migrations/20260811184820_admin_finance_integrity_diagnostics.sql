begin;

drop function if exists api.get_admin_finance_integrity(
  integer,
  smallint,
  smallint
);

create function api.get_admin_finance_integrity(
  page_size integer default 120,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  integrity_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_document_count integer,
  revenue_row_count integer,
  revenue_direct_count integer,
  revenue_reconciled_count integer,
  revenue_pending_count integer,
  expense_document_count integer,
  expense_report_count integer,
  expense_line_count integer,
  expense_direct_count integer,
  expense_reconciled_count integer,
  expense_pending_count integer,
  diagnostic_status text,
  diagnostic_note text,
  methodology_version text
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

  if fiscal_year_from < 1900
     or fiscal_year_from > effective_year_to
     or effective_year_to > 2200 then
    raise exception 'intervalo fiscal invalido'
      using errcode = '22023';
  end if;

  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  with bodies as materialized (
    select distinct on (body.id)
      body.id,
      body.name
    from org.public_bodies as body
    where body.body_type = 'executive'
    order by body.id, body.version desc, body.created_at desc
  ),
  months as materialized (
    select generate_series(
      make_date(fiscal_year_from, 1, 1),
      least(
        make_date(effective_year_to, 12, 1),
        date_trunc('month', current_date)::date
      ),
      interval '1 month'
    )::date as period_start
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
        and extract(year from revenue.revenue_date)::smallint
          between fiscal_year_from and effective_year_to
    ) as versioned
    where versioned.current_row = 1
  ),
  expense_current as materialized (
    select distinct on (report.source_document_artifact_id)
      report.*
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and report.source_document_artifact_id is not null
      and extract(year from report.period_end)::smallint
        between fiscal_year_from and effective_year_to
    order by report.source_document_artifact_id, report.version desc,
      report.created_at desc, report.id desc
  ),
  lineage_pairs as materialized (
    select distinct
      revenue.origin_raw_record_id,
      revenue.source_document_artifact_id
    from revenue_current as revenue
    union
    select distinct
      report.origin_raw_record_id,
      report.source_document_artifact_id
    from expense_current as report
  ),
  direct_pairs as materialized (
    select
      pair.origin_raw_record_id,
      pair.source_document_artifact_id,
      finance.has_direct_document_lineage(
        pair.origin_raw_record_id,
        pair.source_document_artifact_id
      ) as is_direct
    from lineage_pairs as pair
  ),
  lineage_statuses as materialized (
    select
      pair.origin_raw_record_id,
      pair.source_document_artifact_id,
      case
        when pair.is_direct then 'direct'::text
        when finance.has_exact_document_lineage(
          pair.origin_raw_record_id,
          pair.source_document_artifact_id
        ) then 'reconciled'::text
        else 'pending'::text
      end as lineage_status
    from direct_pairs as pair
  ),
  revenue_months as materialized (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      count(distinct revenue.source_document_artifact_id)::integer
        as document_count,
      count(*)::integer as row_count,
      count(*) filter (
        where lineage.lineage_status = 'direct'
      )::integer as direct_count,
      count(*) filter (
        where lineage.lineage_status = 'reconciled'
      )::integer as reconciled_count,
      count(*) filter (
        where lineage.lineage_status = 'pending'
      )::integer as pending_count
    from revenue_current as revenue
    join lineage_statuses as lineage
      on lineage.origin_raw_record_id = revenue.origin_raw_record_id
     and lineage.source_document_artifact_id
       = revenue.source_document_artifact_id
    group by revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date
  ),
  expense_line_counts as materialized (
    select
      line.report_id,
      count(*)::integer as line_count
    from finance.expense_lines as line
    join expense_current as report on report.id = line.report_id
    group by line.report_id
  ),
  expense_months as materialized (
    select
      report.public_body_id,
      date_trunc('month', report.period_end)::date as period_start,
      count(distinct report.source_document_artifact_id)::integer
        as document_count,
      count(*)::integer as report_count,
      coalesce(sum(lines.line_count), 0)::integer as line_count,
      count(*) filter (
        where lineage.lineage_status = 'direct'
      )::integer as direct_count,
      count(*) filter (
        where lineage.lineage_status = 'reconciled'
      )::integer as reconciled_count,
      count(*) filter (
        where lineage.lineage_status = 'pending'
      )::integer as pending_count
    from expense_current as report
    join lineage_statuses as lineage
      on lineage.origin_raw_record_id = report.origin_raw_record_id
     and lineage.source_document_artifact_id
       = report.source_document_artifact_id
    left join expense_line_counts as lines on lines.report_id = report.id
    group by report.public_body_id,
      date_trunc('month', report.period_end)::date
  )
  select
    body.id::text || ':' || months.period_start::text,
    extract(year from months.period_start)::smallint,
    months.period_start,
    (months.period_start + interval '1 month - 1 day')::date,
    body.name,
    coalesce(revenue.document_count, 0),
    coalesce(revenue.row_count, 0),
    coalesce(revenue.direct_count, 0),
    coalesce(revenue.reconciled_count, 0),
    coalesce(revenue.pending_count, 0),
    coalesce(expense.document_count, 0),
    coalesce(expense.report_count, 0),
    coalesce(expense.line_count, 0),
    coalesce(expense.direct_count, 0),
    coalesce(expense.reconciled_count, 0),
    coalesce(expense.pending_count, 0),
    case
      when coalesce(revenue.pending_count, 0)
        + coalesce(expense.pending_count, 0) > 0
        then 'blocked'::text
      when coalesce(revenue.document_count, 0) > 1
        or coalesce(expense.document_count, 0) > 1
        then 'needs_review'::text
      when coalesce(revenue.document_count, 0) = 1
        and coalesce(expense.document_count, 0) = 1
        then 'ready'::text
      else 'needs_data'::text
    end,
    case
      when coalesce(revenue.pending_count, 0)
        + coalesce(expense.pending_count, 0) > 0
        then 'Ha valores sem vinculo confirmado com o registro bruto e o PDF exatos; eles devem permanecer fora da publicacao.'
      when coalesce(revenue.document_count, 0) > 1
        or coalesce(expense.document_count, 0) > 1
        then 'Ha mais de um documento da mesma competencia; e preciso reconciliar as versoes antes de tratar o mes como fechado.'
      when coalesce(revenue.document_count, 0) = 1
        and coalesce(expense.document_count, 0) = 1
        then 'Receita e despesa possuem documentos oficiais e linhagem verificavel para esta competencia.'
      when coalesce(revenue.document_count, 0) = 0
        and coalesce(expense.document_count, 0) = 0
        then 'Nenhum relatorio validado foi publicado para este mes; isso nao significa valor zero.'
      when coalesce(revenue.document_count, 0) = 0
        then 'Ha despesa publicada, mas ainda falta o documento comparavel de receita.'
      else 'Ha receita publicada, mas ainda falta o documento comparavel de despesa.'
    end,
    'admin-finance-integrity/1.0.0'::text
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

revoke all on function api.get_admin_finance_integrity(
  integer,
  smallint,
  smallint
) from public, anon;

grant execute on function api.get_admin_finance_integrity(
  integer,
  smallint,
  smallint
) to authenticated;

comment on function api.get_admin_finance_integrity(
  integer,
  smallint,
  smallint
) is
  'Diagnostico interno mensal de cobertura, duplicidade e linhagem financeira; nao recalcula totais monetarios.';

commit;
