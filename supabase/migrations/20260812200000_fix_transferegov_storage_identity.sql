-- O workflow financeiro autentica com a identidade municipal ativa. A
-- migration inicial do Transferegov vinculou o corredor, por engano, ao
-- usuário técnico do Diário. Corrigimos o vínculo sem apagar a linha nem o
-- histórico de auditoria.

do $migration$
declare
  previous_auth_user_id uuid;
  preserved_status text;
  preserved_can_select boolean;
  preserved_can_insert boolean;
  preserved_activated_at timestamptz;
begin
  if not exists (
    select 1
    from auth.users
    where id = 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'::uuid
  ) then
    raise exception
      'UUID técnico municipal não existe em auth.users';
  end if;

  select
    identity.auth_user_id,
    identity.status,
    identity.can_select,
    identity.can_insert,
    identity.activated_at
  into
    previous_auth_user_id,
    preserved_status,
    preserved_can_select,
    preserved_can_insert,
    preserved_activated_at
  from audit.storage_workload_identities as identity
  where identity.slug = 'transferegov-parcerias-collector'
    and identity.object_prefix = 'transferegov/parcerias/'
  for update;

  if previous_auth_user_id is null then
    raise exception
      'corredor de Storage do Transferegov não foi provisionado';
  end if;

  update audit.storage_workload_identities
  set
    auth_user_id = 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'::uuid,
    metadata = metadata || jsonb_build_object(
      'workflow_identity', 'municipal-transparency',
      'corrected_by', 'migration:fix-transferegov-storage-identity',
      'previous_auth_user_id', previous_auth_user_id
    )
  where slug = 'transferegov-parcerias-collector'
    and object_prefix = 'transferegov/parcerias/';

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
    'migration:fix-transferegov-storage-identity',
    'storage_workload_identity.corrected',
    'audit.storage_workload_identities',
    'transferegov-parcerias-collector',
    jsonb_build_object(
      'auth_user_id', previous_auth_user_id,
      'object_prefix', 'transferegov/parcerias/',
      'status', preserved_status,
      'can_select', preserved_can_select,
      'can_insert', preserved_can_insert,
      'activated_at', preserved_activated_at
    ),
    jsonb_build_object(
      'auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
      'object_prefix', 'transferegov/parcerias/',
      'status', preserved_status,
      'can_select', preserved_can_select,
      'can_insert', preserved_can_insert,
      'activated_at', preserved_activated_at
    ),
    jsonb_build_object(
      'reason', 'align_storage_identity_with_finance_workflow',
      'secret_values_persisted', false
    )
  );
end
$migration$;
