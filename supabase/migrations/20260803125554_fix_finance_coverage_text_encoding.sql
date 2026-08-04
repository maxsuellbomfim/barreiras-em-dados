-- Corrige respostas legadas que chegaram ao banco com mojibake, sem apagar
-- a função calculadora nem alterar os registros históricos.

alter function api.get_public_finance_coverage(integer, smallint, smallint)
  rename to get_public_finance_coverage_calculated;

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
      when calculated.coverage_note like '%Ã%'
        then convert_from(convert_to(calculated.coverage_note, 'LATIN1'), 'UTF8')
      else calculated.coverage_note
    end,
    calculated.calculation_methodology
  from api.get_public_finance_coverage_calculated(
    page_size, fiscal_year_from, fiscal_year_to
  ) as calculated;
$function$;

revoke all on function api.get_public_finance_coverage(integer, smallint, smallint)
  from public;
grant execute on function api.get_public_finance_coverage(integer, smallint, smallint)
  to anon, authenticated;

comment on function api.get_public_finance_coverage(integer, smallint, smallint) is
  'Cobertura mensal financeira pública com correção de texto e ausência distinta de zero.';
