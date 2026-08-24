begin;

drop policy if exists collector_worker_expense_report_conflicts_select
on evidence.source_conflicts;
create policy collector_worker_expense_report_conflicts_select
on evidence.source_conflicts
for select to collector_worker
using (
  target_type = 'finance.expense_reports'
  and (
    field_name in (
      'total_fixed_amount', 'total_additions_amount',
      'total_reductions_amount', 'total_updated_amount',
      'total_committed_period_amount', 'total_committed_to_date_amount',
      'total_liquidated_period_amount', 'total_liquidated_to_date_amount',
      'total_paid_period_amount', 'total_paid_to_date_amount',
      'total_unpaid_committed_amount', 'total_balance_amount'
    )
    or field_name ~ '^budget_unit_subtotal:[0-9]{6,8}:[a-z_]+_amount$'
  )
);

drop policy if exists collector_worker_expense_report_conflicts_insert
on evidence.source_conflicts;
create policy collector_worker_expense_report_conflicts_insert
on evidence.source_conflicts
for insert to collector_worker
with check (
  target_type = 'finance.expense_reports'
  and status = 'open'
  and (
    field_name in (
      'total_fixed_amount', 'total_additions_amount',
      'total_reductions_amount', 'total_updated_amount',
      'total_committed_period_amount', 'total_committed_to_date_amount',
      'total_liquidated_period_amount', 'total_liquidated_to_date_amount',
      'total_paid_period_amount', 'total_paid_to_date_amount',
      'total_unpaid_committed_amount', 'total_balance_amount'
    )
    or (
      field_name = concat(
        'budget_unit_subtotal:',
        first_value ->> 'budget_unit_code',
        ':',
        first_value ->> 'field_name'
      )
      and first_value ->> 'scope' = 'budget_unit_subtotal'
      and second_value ->> 'scope' = 'budget_unit_subtotal'
      and first_value ->> 'budget_unit_code'
        ~ '^[0-9]{6,8}$'
      and first_value ->> 'budget_unit_code'
        = second_value ->> 'budget_unit_code'
      and first_value ->> 'budget_unit_name'
        = second_value ->> 'budget_unit_name'
      and nullif(first_value ->> 'budget_unit_name', '') is not null
      and first_value ->> 'field_name'
        ~ '^[a-z_]+_amount$'
      and first_value ->> 'field_name'
        = second_value ->> 'field_name'
      and second_value ->> 'difference_amount'
        ~ '^-?[0-9]+([.][0-9]{1,2})?$'
      and abs((second_value ->> 'difference_amount')::numeric) <= 0.10
    )
  )
);

drop function if exists api.get_public_expense_report_source_conflicts(
  integer,
  smallint
);

create function api.get_public_expense_report_source_conflicts(
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
  with ranked_reports as materialized (
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

revoke all on function api.get_public_expense_report_source_conflicts(
  integer,
  smallint
) from public;
grant execute on function api.get_public_expense_report_source_conflicts(
  integer,
  smallint
) to anon, authenticated;

comment on function api.get_public_expense_report_source_conflicts(
  integer,
  smallint
) is
  'Divergencias aritmeticas literais entre linhas, subtotais por unidade e o Total geral dos demonstrativos de despesas.';

commit;
