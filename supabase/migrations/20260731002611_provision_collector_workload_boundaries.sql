begin;

-- Identidade PostgreSQL específica do primeiro coletor. Ela nasce sem LOGIN;
-- a senha e a ativação pertencem ao procedimento operacional, nunca à migration.
do $migration$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'collector_querido_diario'
  ) then
    create role collector_querido_diario
      nologin
      inherit
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls
      connection limit 2;
  elsif exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'collector_querido_diario'
      and (
        rolcanlogin
        or rolsuper
        or rolcreatedb
        or rolcreaterole
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception
      'collector_querido_diario exists with unsafe attributes';
  end if;
end
$migration$;

alter role collector_querido_diario
  nologin
  inherit
  connection limit 2;

alter role collector_querido_diario set statement_timeout = '15s';
alter role collector_querido_diario set lock_timeout = '5s';
alter role collector_querido_diario
  set idle_in_transaction_session_timeout = '15s';
alter role collector_querido_diario
  set search_path = source, raw, pg_catalog;

grant collector_worker to collector_querido_diario;

-- Mapeamento interno entre um usuário técnico do Auth e o único prefixo que
-- ele pode criar/restaurar. Nenhum usuário é cadastrado pela migration.
create table audit.storage_workload_identities (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (
    slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'
  ),
  auth_user_id uuid not null unique
    references auth.users (id) on delete cascade,
  bucket_id text not null check (bucket_id = 'raw-artifacts'),
  object_prefix text not null check (
    object_prefix = 'querido-diario/gazettes/'
  ),
  can_select boolean not null default true,
  can_insert boolean not null default true,
  status text not null default 'pending' check (
    status in ('pending', 'active', 'suspended', 'retired')
  ),
  activated_at timestamptz,
  expires_at timestamptz,
  metadata jsonb not null default '{}'::jsonb check (
    jsonb_typeof(metadata) = 'object'
  ),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (status <> 'active' or activated_at is not null),
  check (expires_at is null or expires_at > created_at)
);

create trigger storage_workload_identities_set_updated_at
before update on audit.storage_workload_identities
for each row execute function audit.set_updated_at();

alter table audit.storage_workload_identities enable row level security;
alter table audit.storage_workload_identities force row level security;

revoke all on table audit.storage_workload_identities
  from public, anon, authenticated;

-- SECURITY DEFINER é necessário apenas para consultar o mapeamento interno.
-- A função não aceita user_id do chamador: sempre usa auth.uid(), possui
-- search_path vazio e devolve somente um booleano.
create or replace function api.can_access_raw_artifact(
  requested_operation text,
  requested_bucket text,
  requested_name text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select coalesce(
    exists (
      select 1
      from audit.storage_workload_identities as workload
      where workload.auth_user_id = (select auth.uid())
        and workload.status = 'active'
        and workload.activated_at <= statement_timestamp()
        and (
          workload.expires_at is null
          or workload.expires_at > statement_timestamp()
        )
        and workload.bucket_id = requested_bucket
        and starts_with(requested_name, workload.object_prefix)
        and case requested_operation
          when 'select' then workload.can_select
          when 'insert' then workload.can_insert
          else false
        end
    ),
    false
  );
$function$;

revoke all on function api.can_access_raw_artifact(text, text, text)
  from public, anon, authenticated;
grant execute on function api.can_access_raw_artifact(text, text, text)
  to authenticated;

create policy raw_artifacts_workload_select
on storage.objects
for select
to authenticated
using (
  api.can_access_raw_artifact('select', bucket_id, name)
);

create policy raw_artifacts_workload_insert
on storage.objects
for insert
to authenticated
with check (
  api.can_access_raw_artifact('insert', bucket_id, name)
);

comment on table audit.storage_workload_identities is
  'Allowlist interna de identidades técnicas do Storage; sem dados editoriais.';
comment on function api.can_access_raw_artifact(text, text, text) is
  'Autoriza somente o usuário Auth ativo, o bucket e o prefixo registrados.';

commit;
