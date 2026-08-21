begin;

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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  ranked as (
    select
      revenue.*,
      row_number() over (
        partition by revenue.public_body_id,
          coalesce(revenue.external_id, revenue.id::text)
        order by revenue.version desc, revenue.created_at desc, revenue.id desc
      ) as current_row
    from finance.revenues as revenue
    join exact_lineage as lineage
      on lineage.origin_raw_record_id = revenue.origin_raw_record_id
     and lineage.document_artifact_id = revenue.source_document_artifact_id
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
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
  'Receitas validadas com sinal contábil e vínculo exato entre registro bruto e PDF, resolvido em conjunto.';

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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  current_reports as (
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
  'Linhas de despesa do relatório vigente com origem bruta e PDF exatos, resolvidos em conjunto.';

commit;
