-- Corrige notas de cobertura que chegaram ao banco com dupla interpretação UTF-8.
-- A conversão é condicional para permanecer idempotente caso a função interna já
-- esteja armazenando texto UTF-8 correto em uma próxima versão.

alter function api.get_public_monthly_finance_closures(integer, smallint)
  rename to get_public_monthly_finance_closures_calculated;

create function api.get_public_monthly_finance_closures(
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
language sql
stable
security definer
set search_path = ''
as $function$
  select
    calculated.closure_id,
    calculated.fiscal_year,
    calculated.period_start,
    calculated.period_end,
    calculated.public_body_name,
    calculated.revenue_report_amount,
    calculated.revenue_report_count,
    calculated.revenue_line_count,
    calculated.expense_paid_amount,
    calculated.expense_committed_amount,
    calculated.expense_liquidated_amount,
    calculated.expense_report_count,
    calculated.operational_difference_amount,
    calculated.closure_status,
    case
      when calculated.coverage_note like '%Ã%'
        then convert_from(convert_to(calculated.coverage_note, 'LATIN1'), 'UTF8')
      else calculated.coverage_note
    end,
    calculated.calculation_methodology
  from api.get_public_monthly_finance_closures_calculated(page_size, fiscal_year_filter)
    as calculated
$function$;

revoke all on function api.get_public_monthly_finance_closures(integer, smallint)
  from public;
grant execute on function api.get_public_monthly_finance_closures(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_monthly_finance_closures(integer, smallint) is
  'Fechamento mensal determinístico: relatório de receita versus pagamento efetivado, com cobertura explícita.';
