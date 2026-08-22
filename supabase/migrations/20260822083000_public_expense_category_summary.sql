begin;

create or replace function api.get_public_expense_category_summary(
  report_filter uuid
)
returns table (
  expense_report_id uuid,
  expense_code text,
  source_description text,
  source_description_count integer,
  line_count integer,
  committed_period_amount numeric,
  liquidated_period_amount numeric,
  paid_period_amount numeric,
  report_total_paid_amount numeric,
  aggregated_total_paid_amount numeric,
  reconciliation_status text,
  paid_share_percent numeric,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if report_filter is null then
    raise exception 'report_filter e obrigatorio'
      using errcode = '22004';
  end if;

  return query
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  ),
  eligible_report as materialized (
    select report.*
    from (
      select
        candidate.*,
        row_number() over (
          partition by candidate.source_document_artifact_id
          order by candidate.version desc, candidate.created_at desc, candidate.id desc
        ) as current_row
      from finance.expense_reports as candidate
      join exact_lineage as lineage
        on lineage.origin_raw_record_id = candidate.origin_raw_record_id
       and lineage.document_artifact_id = candidate.source_document_artifact_id
      where candidate.validation_status = 'validated'
        and candidate.published_at is not null
    ) as report
    where report.current_row = 1
      and report.id = report_filter
  ),
  grouped as materialized (
    select
      report.id as expense_report_id,
      line.expense_code,
      min(btrim(line.description)) as source_description,
      count(distinct btrim(line.description))::integer as source_description_count,
      count(*)::integer as line_count,
      coalesce(sum(line.committed_period_amount), 0::numeric) as committed_period_amount,
      coalesce(sum(line.liquidated_period_amount), 0::numeric) as liquidated_period_amount,
      coalesce(sum(line.paid_period_amount), 0::numeric) as paid_period_amount,
      report.total_paid_period_amount as report_total_paid_amount
    from eligible_report as report
    join finance.expense_lines as line
      on line.report_id = report.id
     and line.origin_raw_record_id = report.origin_raw_record_id
    group by report.id, line.expense_code, report.total_paid_period_amount
  ),
  reconciled as materialized (
    select
      grouped.*,
      sum(grouped.paid_period_amount) over (
        partition by grouped.expense_report_id
      ) as aggregated_total_paid_amount
    from grouped
  )
  select
    reconciled.expense_report_id,
    reconciled.expense_code,
    reconciled.source_description,
    reconciled.source_description_count,
    reconciled.line_count,
    reconciled.committed_period_amount,
    reconciled.liquidated_period_amount,
    reconciled.paid_period_amount,
    reconciled.report_total_paid_amount,
    reconciled.aggregated_total_paid_amount,
    case
      when reconciled.aggregated_total_paid_amount = reconciled.report_total_paid_amount
        then 'matched'
      else 'mismatch'
    end,
    case
      when reconciled.aggregated_total_paid_amount = reconciled.report_total_paid_amount
       and reconciled.report_total_paid_amount <> 0::numeric
        then round(
          reconciled.paid_period_amount * 100::numeric
          / reconciled.report_total_paid_amount,
          2
        )
      else null::numeric
    end,
    'public-expense-category-summary/1.0.0'
  from reconciled
  order by reconciled.paid_period_amount desc, reconciled.expense_code asc;
end;
$function$;

revoke all on function api.get_public_expense_category_summary(uuid)
  from public;
grant execute on function api.get_public_expense_category_summary(uuid)
  to anon, authenticated;

comment on function api.get_public_expense_category_summary(uuid) is
  'Agrega todas as linhas do relatorio de despesa vigente por codigo e so calcula participacao quando a soma reconcilia exatamente com o total pago publicado.';

commit;
