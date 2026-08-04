begin;

-- O worker lê o fechamento já calculado para produzir apenas texto explicativo.
-- A função permanece SECURITY DEFINER e a projeção pública continua limitada a
-- anon/authenticated; este grant não expõe tabelas internas.
grant usage on schema api to collector_worker;
grant execute on function api.get_public_monthly_finance_closures(integer, smallint)
  to collector_worker;

commit;
