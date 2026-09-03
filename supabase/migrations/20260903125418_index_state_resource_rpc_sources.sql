begin;

set local statement_timeout = '120s';
set local lock_timeout = '5s';

-- The public LOA view accepts both validated extractor versions. The previous
-- partial indexes covered one version each, so PostgreSQL could not prove that
-- either index satisfied the combined ANY predicate and scanned every
-- extraction result on each public request.
create index extraction_results_bahia_state_loa_all_valid_idx
on raw.extraction_results (
  (result_payload ->> 'source_artifact_sha256'),
  (result_payload ->> 'evidence_sha256'),
  (
    case extractor_version
      when 'bahia-state-loa-barreiras/1.2.0' then 2
      else 1
    end
  ) desc,
  created_at desc,
  id desc
)
include (extraction_job_id)
where candidate_type = 'bahia_state_loa_authorized_amendment'
  and extractor_version = any(array[
    'bahia-state-loa-barreiras/1.1.0'::text,
    'bahia-state-loa-barreiras/1.2.0'::text
  ])
  and validator_version = 'bahia-state-loa-deterministic/1.0.0'
  and validation_status = 'valid'
  and validation_errors = '[]'::jsonb;

-- Payments use DISTINCT ON (payment_id) to retain the latest official
-- observation. Restrict the scan to this validated candidate family and keep
-- the ordering expressions in the index used by that operation.
create index extraction_results_bahia_special_transfer_payment_valid_idx
on raw.extraction_results (
  (btrim(result_payload ->> 'payment_id')),
  ((result_payload ->> 'source_collected_at')) desc,
  created_at desc,
  id desc
)
include (extraction_job_id)
where candidate_type = 'bahia_special_transfer_payment_candidate'
  and extractor_version = 'bahia-special-transfer-payment/1.0.0'
  and validator_version =
    'bahia-special-transfer-territorial-deterministic/1.0.0'
  and validation_status = 'valid'
  and result_payload ->> 'schema_name' =
    'bahia-special-transfer-payment-candidate'
  and result_payload ->> 'schema_version' = '1.0.0';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:index-state-resource-rpc-sources',
  'performance.public_state_resource_sources_indexed',
  'raw.extraction_results',
  gen_random_uuid(),
  jsonb_build_object(
    'loa_combined_versions_indexed', true,
    'special_transfer_candidates_indexed', true
  ),
  jsonb_build_object(
    'public_contract_changed', false,
    'source_data_changed', false
  )
);

commit;
