begin;

-- A sonda horária do CI (cron :17, que o GitHub dispara por volta das :20)
-- regenera várias páginas de uma vez. Às :20 ela coincidia com o refresh da
-- projeção de linhagem, que passava de ~3 s para 7–9 s, e até consultas de
-- 17 ms passavam dos 3 s do papel anônimo (17/10/2026). O refresh passa para
-- :05, :15, :25... e sai dessa janela. Mesma frequência.
do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-exact-document-lineage-pairs-snapshot', '5-55/10 * * * *',
      'select finance.refresh_exact_document_lineage_pairs_snapshot()');
  end if;
end;
$schedule$;

commit;
