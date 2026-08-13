-- O workflow financeiro autentica com a identidade municipal ativa. A
-- migration inicial das emendas estaduais vinculou o corredor ao usuário
-- técnico anterior. Corrigimos somente esse vínculo, sem apagar a linha nem
-- ampliar o prefixo permitido.

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
  where identity.slug = 'bahia-state-amendments-collector'
    and identity.object_prefix = 'bahia/emendas-estaduais/'
  for update;

  if previous_auth_user_id is null then
    raise exception
      'corredor de Storage das emendas estaduais não foi provisionado';
  end if;

  update audit.storage_workload_identities
  set
    auth_user_id = 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a'::uuid,
    metadata = metadata || jsonb_build_object(
      'workflow_identity', 'municipal-transparency',
      'corrected_by', 'migration:fix-bahia-state-storage-identity',
      'previous_auth_user_id', previous_auth_user_id
    )
  where slug = 'bahia-state-amendments-collector'
    and object_prefix = 'bahia/emendas-estaduais/';

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
    'migration:fix-bahia-state-storage-identity',
    'storage_workload_identity.corrected',
    'audit.storage_workload_identities',
    'bahia-state-amendments-collector',
    jsonb_build_object(
      'auth_user_id', previous_auth_user_id,
      'object_prefix', 'bahia/emendas-estaduais/',
      'status', preserved_status,
      'can_select', preserved_can_select,
      'can_insert', preserved_can_insert,
      'activated_at', preserved_activated_at
    ),
    jsonb_build_object(
      'auth_user_id', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
      'object_prefix', 'bahia/emendas-estaduais/',
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
