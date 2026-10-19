begin;

-- Indício de empresa recém-aberta recalculado todo dia às 07:40 (fora da
-- janela :17-:23 da sonda horária).
do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-supplier-opening-signals', '40 7 * * *',
      'select analysis.refresh_supplier_opening_signals()');
  end if;
end;
$schedule$;

commit;
