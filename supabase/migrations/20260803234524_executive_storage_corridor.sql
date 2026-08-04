-- Corredor restrito para o bruto das páginas do Executivo municipal.
-- Mantém os corredores existentes e autoriza somente o prefixo exato.
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
        'prefeitura/executivo/'
      ]
    )
  );

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
  'prefeitura-executive-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'prefeitura/executivo/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'municipal_executive_raw_artifacts',
    'scope', 'prefeito_vice_secretarias_barreiras',
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
  'migration:executive-storage-corridor',
  'storage_workload_identity.activated',
  'audit.storage_workload_identities',
  identity.slug,
  jsonb_build_object(
    'bucket_id', identity.bucket_id,
    'object_prefix', identity.object_prefix,
    'can_select', identity.can_select,
    'can_insert', identity.can_insert,
    'can_update', false,
    'can_delete', false
  ),
  jsonb_build_object(
    'source', 'explicit-executive-collector-corridor',
    'secret_values_persisted', false
  )
from audit.storage_workload_identities identity
where identity.slug = 'prefeitura-executive-collector';;
