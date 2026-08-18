begin;

-- A primeira coleta da CGU (18/08/2026 05:09 UTC) falhou com PersistenceError:
-- o prefixo cgu/emendas-federais/ nao estava na lista fechada de corredores do
-- bucket raw-artifacts e o Content-Type real do ZIP oficial
-- (application/x-zip-compressed) nao estava entre os MIME permitidos. Esta
-- migration abre somente esse corredor para a identidade municipal usada pelo
-- workflow financeiro, sem ampliar nenhum outro privilegio.

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
        'cgu/emendas-federais/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; inclui o ZIP nacional privado de emendas federais da CGU.';

update storage.buckets
set allowed_mime_types = array(
  select distinct mime_type
  from unnest(
    coalesce(allowed_mime_types, array[]::text[])
    || array['application/x-zip-compressed']::text[]
  ) as mime_type
  order by mime_type
)
where id = 'raw-artifacts';

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
  'cgu-federal-amendments-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'cgu/emendas-federais/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'cgu_federal_amendment_raw_artifacts',
    'workflow_identity', 'municipal-transparency',
    'territorial_scope', 'national_archive_filtered_to_2903201_in_records',
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
values (
  'administrator',
  'migration:provision-cgu-storage-corridor',
  'storage_workload_identity.provisioned',
  'audit.storage_workload_identities',
  'cgu-federal-amendments-collector',
  jsonb_build_object(
    'auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
    'bucket_id', 'raw-artifacts',
    'object_prefix', 'cgu/emendas-federais/',
    'can_select', true,
    'can_insert', true,
    'status', 'active'
  ),
  jsonb_build_object(
    'reason', 'first_cgu_collection_failed_on_missing_corridor_and_mime',
    'added_mime_type', 'application/x-zip-compressed',
    'secret_values_persisted', false
  )
);

commit;
