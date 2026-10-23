begin;

-- Aggregate the per-year snapshots, not the recent-month RPC or filter_year=0
-- (the latter is itself capped at 120 months by the existing refresh function).
-- Only the same operational closures already eligible for public comparison count.
create or replace function api.get_public_annual_finance_summary()
returns table (
  fiscal_year smallint,
  comparable_month_count integer,
  first_period_start date,
  last_period_start date,
  revenue_amount text,
  paid_amount text,
  operational_difference_amount text,
  is_full_calendar_year boolean
)
language plpgsql stable security definer set search_path = ''
as $$
begin
  if exists (
    select 1 from generate_series(2021,
      extract(year from statement_timestamp() at time zone 'America/Bahia')::integer) y
    where not exists (
      select 1 from finance.monthly_finance_closure_snapshot_state s where s.filter_year = y
    )
  ) then
    raise exception 'Resumo anual temporariamente indisponível' using errcode = '55000';
  end if;

  if exists (
    select 1 from finance.monthly_finance_closure_snapshot s
    where s.filter_year > 0 and s.closure_status = 'operational'
    group by s.fiscal_year
    having count(*) <> count(distinct s.period_start)
      or bool_or(s.fiscal_year is null or s.period_start is null
        or s.filter_year <> s.fiscal_year
        or s.revenue_report_amount is null or s.expense_paid_amount is null
        or extract(year from s.period_start) <> s.fiscal_year
        or extract(day from s.period_start) <> 1
        or s.revenue_report_amount::text in ('NaN', 'Infinity', '-Infinity')
        or s.expense_paid_amount::text in ('NaN', 'Infinity', '-Infinity')
        or s.revenue_report_amount <> round(s.revenue_report_amount, 2)
        or s.expense_paid_amount <> round(s.expense_paid_amount, 2))
  ) then
    raise exception 'Fechamentos anuais inconsistentes' using errcode = '55000';
  end if;

  return query
    select s.fiscal_year, count(*)::integer,
      min(s.period_start), max(s.period_start),
      round(sum(s.revenue_report_amount), 2)::text,
      round(sum(s.expense_paid_amount), 2)::text,
      round(sum(s.revenue_report_amount) - sum(s.expense_paid_amount), 2)::text,
      count(*) = 12
        and min(s.period_start) = make_date(s.fiscal_year, 1, 1)
        and max(s.period_start) = make_date(s.fiscal_year, 12, 1)
    from finance.monthly_finance_closure_snapshot s
    where s.filter_year = s.fiscal_year and s.closure_status = 'operational'
    group by s.fiscal_year
    order by s.fiscal_year desc;
end;
$$;

revoke all on function api.get_public_annual_finance_summary() from public;
grant execute on function api.get_public_annual_finance_summary() to anon, authenticated;
comment on function api.get_public_annual_finance_summary() is
  'Exact annual totals of all operational public monthly closures; independent of recent-list pagination. No raw documents or private identifiers.';
notify pgrst, 'reload schema';
commit;
