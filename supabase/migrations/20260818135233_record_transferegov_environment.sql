begin;

-- Comunicado 23/2026 (Transferegov/ObrasGov): o ambiente que permanece e o
-- api-publica.transferegov.gestao.gov.br; os hosts legados
-- (repositorio.dados.gov.br/seges/detru, docs.api.transferegov, api.obrasgov)
-- serao desligados em 31/08/2026. Este repositorio nunca usou os hosts
-- legados. Verificacao em 18/08/2026: sondas 200 na API de parcerias, no
-- catalogo Azure e no ZIP historico, alem de execucao completa do workflow.
-- Esta migration apenas registra o contrato verificado nos endpoints.

update source.source_endpoints as endpoint
set config = coalesce(endpoint.config, '{}'::jsonb) || jsonb_build_object(
  'api_environment', 'api-publica.transferegov.gestao.gov.br',
  'environment_contract', 'comunicado-23-2026',
  'environment_verified_on', '2026-08-18',
  'legacy_hosts_never_used', true,
  'migration_notice_url',
    'https://www.gov.br/obrasgov/pt-br/noticias/2026/comunicado-23-2026-mudancas-nos-acessos-as-apis-de-dados-abertos-do-transferegov-br-e-do-obrasgov-br'
)
from source.data_sources as source
where source.id = endpoint.data_source_id
  and source.slug in ('transferegov-parcerias', 'transferegov-downloads');

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
select
  'administrator',
  'migration:record-transferegov-environment',
  'source_endpoint.contract_verified',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'api_environment', endpoint.config ->> 'api_environment',
    'environment_verified_on', endpoint.config ->> 'environment_verified_on'
  ),
  jsonb_build_object(
    'reason', 'comunicado_23_2026_discontinues_legacy_hosts_on_2026-08-31',
    'verification', 'live_probes_200_and_full_workflow_run',
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug in ('transferegov-parcerias', 'transferegov-downloads');

commit;
