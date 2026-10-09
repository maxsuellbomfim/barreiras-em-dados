begin;

-- O fechamento mensal (página inicial e /financas) recalcula a cada visita a
-- linhagem documental e a deduplicação de versões de receita e despesa:
-- 2,2 s com cache frio em 09/10/2026 e cancelado pelos 3 s do papel anônimo
-- na janela da sonda pública (o cartão "entrou/saiu" some). Os números só
-- mudam quando chega relatório novo. Um instantâneo por filtro de ano é
-- refeito de hora em hora pelo pg_cron e a função pública lê dele; filtro
-- ainda sem instantâneo cai no cálculo ao vivo, com as mesmas regras
-- (monthly-finance-closure/1.1.0). Cache de leitura, não registro: o cálculo
-- continua em api.get_public_monthly_finance_closures_calculated.
create table finance.monthly_finance_closure_snapshot (
  filter_year smallint not null check (filter_year = 0 or filter_year between 2000 and 2100),
  row_order integer not null check (row_order between 1 and 120),
  closure_id text not null,
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
  calculation_methodology text,
  primary key (filter_year, row_order)
);

-- Um filtro só é servido do instantâneo depois de calculado (inclusive
-- quando o resultado é vazio).
create table finance.monthly_finance_closure_snapshot_state (
  filter_year smallint primary key check (filter_year = 0 or filter_year between 2000 and 2100),
  row_count integer not null check (row_count >= 0),
  computed_at timestamptz not null
);

alter table finance.monthly_finance_closure_snapshot enable row level security;
alter table finance.monthly_finance_closure_snapshot force row level security;
alter table finance.monthly_finance_closure_snapshot_state enable row level security;
alter table finance.monthly_finance_closure_snapshot_state force row level security;
revoke all on finance.monthly_finance_closure_snapshot from public, anon, authenticated;
revoke all on finance.monthly_finance_closure_snapshot_state from public, anon, authenticated;

comment on table finance.monthly_finance_closure_snapshot is
  'Instantâneo de api.get_public_monthly_finance_closures_calculated por filtro de ano (0 = sem filtro), refeito de hora em hora; cache de leitura, não registro.';

create function finance.refresh_monthly_finance_closure_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  filter_value smallint;
  refreshed integer := 0;
  filter_rows integer;
begin
  perform pg_advisory_xact_lock(hashtext('finance.monthly_finance_closure_snapshot'));
  delete from finance.monthly_finance_closure_snapshot;
  delete from finance.monthly_finance_closure_snapshot_state;
  -- 0 = sem filtro; depois cada ano de 2021 até o corrente.
  for filter_value in
    select 0::smallint
    union all
    select year_value::smallint
    from generate_series(
      2021,
      extract(year from statement_timestamp() at time zone 'America/Bahia')::integer
    ) as year_value
  loop
    insert into finance.monthly_finance_closure_snapshot (
      filter_year, row_order, closure_id, fiscal_year, period_start, period_end,
      public_body_name, revenue_report_amount, revenue_report_count,
      revenue_line_count, expense_paid_amount, expense_committed_amount,
      expense_liquidated_amount, expense_report_count,
      operational_difference_amount, closure_status, coverage_note,
      calculation_methodology
    )
    select
      filter_value, calculated.row_order::integer, calculated.closure_id,
      calculated.fiscal_year, calculated.period_start, calculated.period_end,
      calculated.public_body_name, calculated.revenue_report_amount,
      calculated.revenue_report_count, calculated.revenue_line_count,
      calculated.expense_paid_amount, calculated.expense_committed_amount,
      calculated.expense_liquidated_amount, calculated.expense_report_count,
      calculated.operational_difference_amount, calculated.closure_status,
      calculated.coverage_note, calculated.calculation_methodology
    from api.get_public_monthly_finance_closures_calculated(
      120, nullif(filter_value, 0::smallint)
    ) with ordinality as calculated(
      closure_id, fiscal_year, period_start, period_end, public_body_name,
      revenue_report_amount, revenue_report_count, revenue_line_count,
      expense_paid_amount, expense_committed_amount, expense_liquidated_amount,
      expense_report_count, operational_difference_amount, closure_status,
      coverage_note, calculation_methodology, row_order
    );
    get diagnostics filter_rows = row_count;
    insert into finance.monthly_finance_closure_snapshot_state (
      filter_year, row_count, computed_at
    ) values (filter_value, filter_rows, statement_timestamp());
    refreshed := refreshed + filter_rows;
  end loop;
  return refreshed;
end;
$function$;

revoke all on function finance.refresh_monthly_finance_closure_snapshot()
  from public, anon, authenticated;

create or replace function api.get_public_monthly_finance_closures(
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
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if page_size < 1 or page_size > 120 then
    raise exception 'page_size deve estar entre 1 e 120' using errcode = '22023';
  end if;
  if exists (
    select 1
    from finance.monthly_finance_closure_snapshot_state as state
    where state.filter_year = coalesce(fiscal_year_filter, 0::smallint)
  ) then
    return query
    select
      snapshot.closure_id, snapshot.fiscal_year, snapshot.period_start,
      snapshot.period_end, snapshot.public_body_name,
      snapshot.revenue_report_amount, snapshot.revenue_report_count,
      snapshot.revenue_line_count, snapshot.expense_paid_amount,
      snapshot.expense_committed_amount, snapshot.expense_liquidated_amount,
      snapshot.expense_report_count, snapshot.operational_difference_amount,
      snapshot.closure_status,
      case
        when snapshot.coverage_note like '%Ã%'
          then convert_from(convert_to(snapshot.coverage_note, 'LATIN1'), 'UTF8')
        else snapshot.coverage_note
      end,
      snapshot.calculation_methodology
    from finance.monthly_finance_closure_snapshot as snapshot
    where snapshot.filter_year = coalesce(fiscal_year_filter, 0::smallint)
    order by snapshot.row_order
    limit page_size;
    return;
  end if;
  return query
  select
    calculated.closure_id, calculated.fiscal_year, calculated.period_start,
    calculated.period_end, calculated.public_body_name,
    calculated.revenue_report_amount, calculated.revenue_report_count,
    calculated.revenue_line_count, calculated.expense_paid_amount,
    calculated.expense_committed_amount, calculated.expense_liquidated_amount,
    calculated.expense_report_count, calculated.operational_difference_amount,
    calculated.closure_status,
    case
      when calculated.coverage_note like '%Ã%'
        then convert_from(convert_to(calculated.coverage_note, 'LATIN1'), 'UTF8')
      else calculated.coverage_note
    end,
    calculated.calculation_methodology
  from api.get_public_monthly_finance_closures_calculated(page_size, fiscal_year_filter)
    as calculated;
end;
$function$;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-monthly-finance-closure-snapshot', '50 * * * *',
      'select finance.refresh_monthly_finance_closure_snapshot()');
  end if;
end;
$schedule$;

notify pgrst, 'reload schema';

commit;
