-- Associate each executive portrait with the nearest following official heading.
-- Existing raw records remain immutable; the next collection creates a new
-- parser version and the public projection can select the latest snapshot.
update source.source_endpoints
set config = jsonb_set(
  coalesce(config, '{}'::jsonb),
  '{parser_version}',
  to_jsonb('barreiras-executive-pages/1.1.1'::text),
  true
)
where slug = 'executive-pages-html'
  and data_source_id = (
    select id
    from source.data_sources
    where slug = 'prefeitura-barreiras'
  );
