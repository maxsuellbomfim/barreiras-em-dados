begin;

-- As retenções da folha (/financas/retencoes) recalculavam a cada visita as
-- grades mensais de empenho e pagamento do WebRun: 4,4 s com cache frio em
-- 13/10/2026, acima dos 3 s do papel anônimo ("Retenções temporariamente
-- indisponíveis" em duas varreduras). Os números só mudam quando a coleta do
-- WebRun preserva grade nova. Um instantâneo por ano (2024 até o corrente) é
-- refeito de hora em hora pelo pg_cron; ano sem instantâneo cai no cálculo ao
-- vivo. Cache de leitura, não registro: a regra continua em
-- api.get_public_payroll_withholdings_calculated.
alter function api.get_public_payroll_withholdings(integer)
  rename to get_public_payroll_withholdings_calculated;
revoke all on function api.get_public_payroll_withholdings_calculated(integer)
  from public, anon, authenticated;

create table finance.payroll_withholdings_snapshot (
  fiscal_year integer not null check (fiscal_year between 2024 and 2100),
  row_order integer not null check (row_order >= 1),
  creditor_name text,
  commitments integer,
  amount text,
  reversal_amount text,
  first_commitment_date date,
  last_commitment_date date,
  latest_commitment_key text,
  grid_artifact_sha256 text,
  year_commitments integer,
  year_amount text,
  year_reversal_amount text,
  year_grid_months integer,
  year_linked_payments integer,
  year_months jsonb,
  source_page_url text,
  methodology_version text,
  primary key (fiscal_year, row_order)
);

create table finance.payroll_withholdings_snapshot_state (
  fiscal_year integer primary key check (fiscal_year between 2024 and 2100),
  row_count integer not null check (row_count >= 0),
  computed_at timestamptz not null
);

alter table finance.payroll_withholdings_snapshot enable row level security;
alter table finance.payroll_withholdings_snapshot force row level security;
alter table finance.payroll_withholdings_snapshot_state enable row level security;
alter table finance.payroll_withholdings_snapshot_state force row level security;
revoke all on finance.payroll_withholdings_snapshot from public, anon, authenticated;
revoke all on finance.payroll_withholdings_snapshot_state from public, anon, authenticated;

comment on table finance.payroll_withholdings_snapshot is
  'Instantâneo de api.get_public_payroll_withholdings_calculated por ano, refeito de hora em hora; cache de leitura, não registro.';

create function finance.refresh_payroll_withholdings_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  year_value integer;
  year_rows integer;
  refreshed integer := 0;
begin
  perform pg_advisory_xact_lock(hashtext('finance.payroll_withholdings_snapshot'));
  delete from finance.payroll_withholdings_snapshot;
  delete from finance.payroll_withholdings_snapshot_state;
  for year_value in
    select generate_series(
      2024,
      extract(year from statement_timestamp() at time zone 'America/Bahia')::integer
    )
  loop
    insert into finance.payroll_withholdings_snapshot (
      fiscal_year, row_order, creditor_name, commitments, amount,
      reversal_amount, first_commitment_date, last_commitment_date,
      latest_commitment_key, grid_artifact_sha256, year_commitments,
      year_amount, year_reversal_amount, year_grid_months,
      year_linked_payments, year_months, source_page_url, methodology_version
    )
    select
      year_value, calculated.row_order::integer, calculated.creditor_name,
      calculated.commitments, calculated.amount, calculated.reversal_amount,
      calculated.first_commitment_date, calculated.last_commitment_date,
      calculated.latest_commitment_key, calculated.grid_artifact_sha256,
      calculated.year_commitments, calculated.year_amount,
      calculated.year_reversal_amount, calculated.year_grid_months,
      calculated.year_linked_payments, calculated.year_months,
      calculated.source_page_url, calculated.methodology_version
    from api.get_public_payroll_withholdings_calculated(year_value)
      with ordinality as calculated(
        creditor_name, commitments, amount, reversal_amount,
        first_commitment_date, last_commitment_date, latest_commitment_key,
        grid_artifact_sha256, year_commitments, year_amount,
        year_reversal_amount, year_grid_months, year_linked_payments,
        year_months, source_page_url, methodology_version, row_order
      );
    get diagnostics year_rows = row_count;
    insert into finance.payroll_withholdings_snapshot_state (fiscal_year, row_count, computed_at)
    values (year_value, year_rows, statement_timestamp());
    refreshed := refreshed + year_rows;
  end loop;
  return refreshed;
end;
$function$;

revoke all on function finance.refresh_payroll_withholdings_snapshot()
  from public, anon, authenticated;

create function api.get_public_payroll_withholdings(p_year integer)
returns table (
  creditor_name text,
  commitments integer,
  amount text,
  reversal_amount text,
  first_commitment_date date,
  last_commitment_date date,
  latest_commitment_key text,
  grid_artifact_sha256 text,
  year_commitments integer,
  year_amount text,
  year_reversal_amount text,
  year_grid_months integer,
  year_linked_payments integer,
  year_months jsonb,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;
  if exists (
    select 1 from finance.payroll_withholdings_snapshot_state as state
    where state.fiscal_year = p_year
  ) then
    return query
    select
      snapshot.creditor_name, snapshot.commitments, snapshot.amount,
      snapshot.reversal_amount, snapshot.first_commitment_date,
      snapshot.last_commitment_date, snapshot.latest_commitment_key,
      snapshot.grid_artifact_sha256, snapshot.year_commitments,
      snapshot.year_amount, snapshot.year_reversal_amount,
      snapshot.year_grid_months, snapshot.year_linked_payments,
      snapshot.year_months, snapshot.source_page_url,
      snapshot.methodology_version
    from finance.payroll_withholdings_snapshot as snapshot
    where snapshot.fiscal_year = p_year
    order by snapshot.row_order;
    return;
  end if;
  return query
  select * from api.get_public_payroll_withholdings_calculated(p_year);
end;
$function$;

revoke all on function api.get_public_payroll_withholdings(integer) from public;
grant execute on function api.get_public_payroll_withholdings(integer)
  to anon, authenticated;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-payroll-withholdings-snapshot', '55 * * * *',
      'select finance.refresh_payroll_withholdings_snapshot()');
  end if;
end;
$schedule$;

notify pgrst, 'reload schema';

commit;
