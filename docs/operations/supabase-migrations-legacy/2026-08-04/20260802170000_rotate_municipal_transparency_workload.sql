-- Rotaciona a identidade técnica do coletor municipal sem apagar o usuário
-- Auth antigo nem registros de auditoria. Senhas e tokens permanecem fora do
-- banco e do repositório.

do $migration$
begin
  if not exists (
    select 1
    from auth.users
    where id = 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'::uuid
  ) then
    raise exception
      'novo UUID técnico municipal não existe em auth.users';
  end if;
end
$migration$;

do $migration$
begin
  update audit.storage_workload_identities
  set
    slug = 'municipal-transparency-collector-retired-20260802',
    status = 'retired',
    can_select = false,
    can_insert = false,
    metadata = metadata || jsonb_build_object(
      'retired_reason', 'credential_rotation',
      'replacement_auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'
    )
  where slug = 'municipal-transparency-collector'
    and auth_user_id = '27b3add6-f788-48e5-bf6f-50dfbd8cf198'::uuid
    and object_prefix = 'municipal-transparency/'
    and status = 'active';

  if found then
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
    values (
      'administrator',
      'migration:rotate_municipal_transparency_workload',
      'storage_workload_identity.retired',
      'audit.storage_workload_identities',
      'municipal-transparency-collector-retired-20260802',
      jsonb_build_object(
        'auth_user_id', '27b3add6-f788-48e5-bf6f-50dfbd8cf198',
        'object_prefix', 'municipal-transparency/',
        'status', 'active'
      ),
      jsonb_build_object(
        'auth_user_id', '27b3add6-f788-48e5-bf6f-50dfbd8cf198',
        'object_prefix', 'municipal-transparency/',
        'status', 'retired',
        'can_select', false,
        'can_insert', false
      ),
      jsonb_build_object(
        'replacement_auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
        'secret_values_persisted', false
      )
    );
  else
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
      'migration:rotate_municipal_transparency_workload',
      'storage_workload_identity.rotation_gap',
      'audit.storage_workload_identities',
      'municipal-transparency-collector',
      jsonb_build_object(
        'previous_auth_user_id', '27b3add6-f788-48e5-bf6f-50dfbd8cf198',
        'status', 'not_present'
      ),
      jsonb_build_object(
        'reason', 'previous_auth_user_deleted_before_rotation',
        'replacement_auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
        'secret_values_persisted', false
      )
    );
  end if;
end
$migration$;

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
  'municipal-transparency-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'municipal-transparency/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'municipal_transparency_raw_artifacts',
    'scope', 'prefeitura_e_camara_barreiras',
    'credentials', 'stored_outside_database_and_repository',
    'rotation_replaces_auth_user_id',
      '27b3add6-f788-48e5-bf6f-50dfbd8cf198'
  )
)
on conflict (auth_user_id, object_prefix) do nothing;

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
values (
  'administrator',
  'migration:rotate_municipal_transparency_workload',
  'storage_workload_identity.activated',
  'audit.storage_workload_identities',
  'municipal-transparency-collector',
  null,
  jsonb_build_object(
    'auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
    'bucket_id', 'raw-artifacts',
    'object_prefix', 'municipal-transparency/',
    'status', 'active',
    'can_select', true,
    'can_insert', true,
    'can_update', false,
    'can_delete', false
  ),
  jsonb_build_object(
    'source', 'responsible-provided-auth-user-uid',
    'secret_values_persisted', false
  )
);
