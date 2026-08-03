-- Usa um marcador ASCII-safe para corrigir respostas cuja migration foi
-- interpretada com codificação legada no banco remoto.

create or replace function api.get_public_finance_coverage(
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
language sql
stable
security definer
set search_path = ''
as $function$
  select
    calculated.coverage_id,
    calculated.fiscal_year,
    calculated.period_start,
    calculated.period_end,
    calculated.public_body_name,
    calculated.revenue_report_count,
    calculated.expense_report_count,
    calculated.coverage_status,
    case
      when position(chr(195) in calculated.coverage_note) > 0
        then convert_from(convert_to(calculated.coverage_note, 'LATIN1'), 'UTF8')
      else calculated.coverage_note
    end,
    calculated.calculation_methodology
  from api.get_public_finance_coverage_calculated(
    page_size, fiscal_year_from, fiscal_year_to
  ) as calculated;
$function$;
