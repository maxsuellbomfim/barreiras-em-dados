-- Prepara a exigencia de MFA para revisores sem bloquear a implantacao.
-- O estado inicial e "observe": contas ativas continuam autorizadas enquanto
-- cadastram TOTP. A mudanca para "required" exige uma sessao AAL2, justificativa
-- e gera uma nova versao append-only mais um evento de auditoria.

create table audit.reviewer_mfa_policy_versions (
  id bigint generated always as identity primary key,
  mode text not null check (mode in ('observe', 'required')),
  changed_by uuid references auth.users (id) on delete restrict,
  justification text not null check (
    length(btrim(justification)) between 20 and 1000
  ),
  created_at timestamptz not null default statement_timestamp(),
  check (mode = 'observe' or changed_by is not null)
);

create index reviewer_mfa_policy_versions_current_idx
  on audit.reviewer_mfa_policy_versions (created_at desc, id desc);

create index reviewer_mfa_policy_versions_changed_by_idx
  on audit.reviewer_mfa_policy_versions (changed_by);

alter table audit.reviewer_mfa_policy_versions enable row level security;
alter table audit.reviewer_mfa_policy_versions force row level security;

revoke all on table audit.reviewer_mfa_policy_versions
  from public, anon, authenticated;

create trigger reject_reviewer_mfa_policy_mutation
before update or delete on audit.reviewer_mfa_policy_versions
for each row execute function audit.reject_mutation();

insert into audit.reviewer_mfa_policy_versions (
  mode,
  changed_by,
  justification
)
values (
  'observe',
  null,
  'Implantacao inicial sem bloqueio enquanto os revisores cadastram MFA.'
);

create or replace function api.current_reviewer_mfa_mode()
returns text
language sql
stable
security definer
set search_path = ''
as $function$
  select coalesce(
    (
      select policy.mode
      from audit.reviewer_mfa_policy_versions as policy
      order by policy.created_at desc, policy.id desc
      limit 1
    ),
    'required'
  );
$function$;

revoke all on function api.current_reviewer_mfa_mode()
  from public, anon, authenticated;

create or replace function api.is_active_reviewer()
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select
    exists (
      select 1
      from audit.reviewer_identities as reviewer
      where reviewer.auth_user_id = (select auth.uid())
        and reviewer.status = 'active'
        and reviewer.activated_at <= statement_timestamp()
    )
    and (
      (select api.current_reviewer_mfa_mode()) = 'observe'
      or coalesce((select auth.jwt() ->> 'aal'), 'aal1') = 'aal2'
    );
$function$;

revoke all on function api.is_active_reviewer() from public, anon;
grant execute on function api.is_active_reviewer() to authenticated;

create or replace function api.set_reviewer_mfa_enforcement(
  require_mfa boolean,
  change_justification text
)
returns table (
  mode text,
  changed_at timestamptz
)
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid := (select auth.uid());
  next_mode text := case when require_mfa then 'required' else 'observe' end;
  normalized_justification text := btrim(coalesce(change_justification, ''));
  inserted_at timestamptz;
begin
  if reviewer_uid is null or not exists (
    select 1
    from audit.reviewer_identities as reviewer
    where reviewer.auth_user_id = reviewer_uid
      and reviewer.status = 'active'
      and reviewer.activated_at <= statement_timestamp()
  ) then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  if coalesce((select auth.jwt() ->> 'aal'), 'aal1') <> 'aal2' then
    raise exception 'alterar a exigencia de MFA requer uma sessao AAL2'
      using errcode = '42501';
  end if;

  if length(normalized_justification) < 20 then
    raise exception 'a justificativa deve ter pelo menos 20 caracteres'
      using errcode = '22023';
  end if;

  if (select api.current_reviewer_mfa_mode()) = next_mode then
    raise exception 'a politica de MFA ja esta em %', next_mode
      using errcode = '22023';
  end if;

  insert into audit.reviewer_mfa_policy_versions (
    mode,
    changed_by,
    justification
  )
  values (
    next_mode,
    reviewer_uid,
    normalized_justification
  )
  returning created_at into inserted_at;

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
    reviewer_uid::text,
    'reviewer_mfa_policy_changed',
    'audit.reviewer_mfa_policy_versions',
    next_mode,
    jsonb_build_object('mode', next_mode),
    jsonb_build_object(
      'justification', normalized_justification,
      'aal', 'aal2'
    )
  );

  return query select next_mode, inserted_at;
end;
$function$;

revoke all on function api.set_reviewer_mfa_enforcement(boolean, text)
  from public, anon;
grant execute on function api.set_reviewer_mfa_enforcement(boolean, text)
  to authenticated;

comment on table audit.reviewer_mfa_policy_versions is
  'Historico append-only da exigencia AAL2 no painel de revisao.';

comment on function api.set_reviewer_mfa_enforcement(boolean, text) is
  'Ativa ou suspende a exigencia AAL2; requer revisor ativo, sessao AAL2 e justificativa.';
