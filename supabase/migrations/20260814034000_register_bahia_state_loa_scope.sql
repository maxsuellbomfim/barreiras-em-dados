begin;

-- Indice interno do universo integral do Anexo I da LOA 2026. Ele nao contem
-- valor nem municipio e nao e uma projecao publica: serve exclusivamente para
-- impedir que uma chave repetida em outro territorio seja atribuida a Barreiras.

create index if not exists bahia_state_loa_2026_scope_key_idx
  on raw.extraction_results (
    (result_payload ->> 'fiscal_year'),
    (result_payload ->> 'author_external_code'),
    (result_payload ->> 'agency_code'),
    (result_payload ->> 'budget_unit_code'),
    (result_payload ->> 'action_code'),
    created_at desc,
    id desc
  )
  where candidate_type = 'bahia_state_loa_2026_scope_row'
    and extractor_version = 'bahia-state-loa-scope/1.0.0'
    and validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and validation_status = 'valid'
    and result_payload ->> 'visibility' = 'private_reconciliation_scope';

comment on index raw.bahia_state_loa_2026_scope_key_idx is
  'Universo privado da LOA 2026 para bloquear reconciliacao territorial quando a chave estadual nao for globalmente unica.';

update source.source_endpoints as endpoint
set config = endpoint.config || jsonb_build_object(
  'statewide_scope_index',
  jsonb_build_object(
    'candidate_type', 'bahia_state_loa_2026_scope_row',
    'parser_version', 'bahia-state-loa-scope/1.0.0',
    'visibility', 'private_reconciliation_scope',
    'financial_values_included', false,
    'municipality_included', false,
    'purpose', 'prove_global_key_uniqueness_before_territorial_reconciliation'
  )
)
from source.data_sources as source
where endpoint.data_source_id = source.id
  and source.slug = 'bahia-seplan-budget'
  and endpoint.slug = 'state-loa-amendment-annexes';

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
  'migration:register-bahia-state-loa-scope',
  'source_endpoint.scope_index_registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'statewide_scope_index', endpoint.config -> 'statewide_scope_index'
  ),
  jsonb_build_object(
    'public_projection_created', false,
    'financial_values_included', false,
    'municipality_included', false,
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'bahia-seplan-budget'
  and endpoint.slug = 'state-loa-amendment-annexes';

commit;
