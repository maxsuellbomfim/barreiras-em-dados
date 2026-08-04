-- A captura do Executivo passou a versionar registros por snapshot bruto.
-- Mantemos a versão anterior para auditoria e identificamos novas capturas
-- com o parser que evita conflito entre páginas oficiais sucessivas.

update source.source_endpoints
set config = jsonb_set(
  coalesce(config, '{}'::jsonb),
  '{parser_version}',
  to_jsonb('barreiras-executive-pages/1.1.0'::text),
  true
)
where slug = 'executive-pages-html'
  and data_source_id = (
    select id
    from source.data_sources
    where slug = 'prefeitura-barreiras'
  );
