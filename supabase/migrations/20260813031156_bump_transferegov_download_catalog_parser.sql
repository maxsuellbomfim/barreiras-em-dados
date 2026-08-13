begin;

-- A versão 1.1 adiciona a rota proxy oficial de download a cada entrada.
-- O XML bruto e as linhas produzidas pela versão 1.0 permanecem imutáveis.
with target as (
  select endpoint.id, endpoint.config as old_config
  from source.source_endpoints as endpoint
  join source.data_sources as source on source.id = endpoint.data_source_id
  where source.slug = 'transferegov-downloads'
    and endpoint.slug = 'dados-abertos-catalogo'
    and endpoint.config ->> 'parser_version'
      is distinct from 'transferegov-download-catalog/1.1.0'
), changed as (
  update source.source_endpoints as endpoint
  set config = jsonb_set(
    endpoint.config,
    '{parser_version}',
    to_jsonb('transferegov-download-catalog/1.1.0'::text),
    true
  )
  from target
  where endpoint.id = target.id
  returning endpoint.id, target.old_config, endpoint.config as new_config
)
insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  before_state,
  after_state,
  metadata
)
select
  'administrator',
  'migration:bump-transferegov-download-catalog-parser',
  'source_endpoint.parser_version_changed',
  'source.source_endpoints',
  changed.id,
  jsonb_build_object(
    'parser_version', changed.old_config ->> 'parser_version'
  ),
  jsonb_build_object(
    'parser_version', changed.new_config ->> 'parser_version'
  ),
  jsonb_build_object(
    'reason', 'download_url added to the normalized catalog entry',
    'raw_artifacts_rewritten', false,
    'previous_records_deleted', false
  )
from changed;

commit;
