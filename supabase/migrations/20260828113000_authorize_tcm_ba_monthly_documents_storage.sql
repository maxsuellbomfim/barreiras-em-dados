begin;

-- PDFs e interações preparatórias do e-TCM usam um corredor privado separado
-- do catálogo mensal. A identidade técnica continua limitada a prefixos
-- explícitos e não recebe acesso ao restante do bucket.
alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'alba/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/',
        'municipal-transparency/',
        'prefeitura/executivo/',
        'transferegov/parcerias/',
        'bahia/emendas-estaduais/',
        'bahia/loa-emendas-estaduais/',
        'bahia/transferencias-especiais/',
        'cgu/emendas-federais/',
        'cgu/sancoes/',
        'siconfi/dca/',
        'tcm-ba/monthly/',
        'tcm-ba/monthly-documents/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores privados fechados por fonte; inclui catálogo e documentos mensais do e-TCM.';

insert into audit.storage_workload_identities (
  slug,
  auth_user_id,
  bucket_id,
  object_prefix,
  can_select,
  can_insert,
  status,
  activated_at,
  metadata
)
values (
  'tcm-ba-monthly-document-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'tcm-ba/monthly-documents/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'tcm_ba_monthly_document_raw_evidence',
    'raw_visibility', 'private',
    'municipality', 'Barreiras',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do update
set
  slug = excluded.slug,
  can_select = excluded.can_select,
  can_insert = excluded.can_insert,
  status = excluded.status,
  activated_at = excluded.activated_at,
  metadata = excluded.metadata;

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
  'migration:authorize-tcm-ba-monthly-documents-storage',
  'storage_workload_identity.activated',
  'audit.storage_workload_identities',
  identity.id,
  jsonb_build_object(
    'slug', identity.slug,
    'bucket_id', identity.bucket_id,
    'object_prefix', identity.object_prefix,
    'status', identity.status
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'secret_values_persisted', false,
    'scope_expansion', 'single_closed_prefix'
  )
from audit.storage_workload_identities as identity
where identity.auth_user_id = 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'
  and identity.object_prefix = 'tcm-ba/monthly-documents/';

commit;