begin;

drop function if exists api.get_public_expense_lines(uuid, integer, integer);

create function api.get_public_expense_lines(
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
    'public-expense-lines/1.0.0'
  from finance.expense_lines as line
  join finance.expense_reports as report
    on report.id = line.report_id
  join raw.raw_records as origin
    on origin.id = line.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = report.source_document_artifact_id
   and document.artifact_kind = 'document'
  where report.validation_status = 'validated'
    and report.published_at is not null
    and (report_filter is null or report.id = report_filter)
  order by line.paid_period_amount desc, line.line_number asc
  limit page_size
  offset page_offset;
end;
$function$;

revoke all on function api.get_public_expense_lines(uuid, integer, integer) from public;
grant execute on function api.get_public_expense_lines(uuid, integer, integer)
  to anon, authenticated;

comment on function api.get_public_expense_lines(uuid, integer, integer) is
  'Linhas de despesas publicadas, ordenadas por pagamento no periodo e ligadas ao relatorio preservado.';

commit;
