-- Ativação operacional do único workload municipal informado pelo responsável.
-- O UUID Auth não é uma senha; nenhuma credencial ou token é armazenado aqui.

do $migration$
begin
  if not exists (
    select 1
    from auth.users
    where id = '27b3add6-f788-48e5-bf6f-50dfbd8cf198'::uuid
  ) then
    raise exception
      'UUID técnico municipal não existe em auth.users';
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
  '27b3add6-f788-48e5-bf6f-50dfbd8cf198',
  'raw-artifacts',
  'municipal-transparency/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'municipal_transparency_raw_artifacts',
    'scope', 'prefeitura_e_camara_barreiras',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do nothing;

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
  'migration:activate_municipal_transparency_workload',
  'storage_workload_identity.activated',
  'audit.storage_workload_identities',
  'municipal-transparency-collector',
  jsonb_build_object(
    'bucket_id', 'raw-artifacts',
    'object_prefix', 'municipal-transparency/',
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
