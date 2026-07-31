-- Etapa 1C, fatia 1: identidades de revisor e leitura da fila de extração.
-- Nenhum usuário é cadastrado pela migration; o cadastro é um ato registrado.
-- A RPC nega com erro explícito quem não é revisor ativo: falha de
-- autorização nunca aparece como "fila vazia".

create table audit.reviewer_identities (
  id uuid primary key default gen_random_uuid(),
  auth_user_id uuid not null unique
    references auth.users (id) on delete cascade,
  display_name text not null check (
    length(btrim(display_name)) between 1 and 120
  ),
  status text not null default 'pending' check (
    status in ('pending', 'active', 'suspended', 'retired')
  ),
  activated_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (status <> 'active' or activated_at is not null)
);

create trigger reviewer_identities_set_updated_at
before update on audit.reviewer_identities
for each row execute function audit.set_updated_at();

alter table audit.reviewer_identities enable row level security;
alter table audit.reviewer_identities force row level security;

revoke all on table audit.reviewer_identities
  from public, anon, authenticated;

create or replace function api.is_active_reviewer()
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from audit.reviewer_identities as reviewer
    where reviewer.auth_user_id = (select auth.uid())
      and reviewer.status = 'active'
      and reviewer.activated_at <= statement_timestamp()
  );
$function$;

revoke all on function api.is_active_reviewer() from public, anon;
grant execute on function api.is_active_reviewer() to authenticated;

create or replace function api.get_extraction_review_queue(
  page_size integer default 20
)
returns table (
  result_id uuid,
  candidate_type text,
  extractor_version text,
  validation_status text,
  result_created_at timestamptz,
  result_payload jsonb,
  artifact_sha256 text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  select
    result.id,
    result.candidate_type,
    result.extractor_version,
    result.validation_status,
    result.created_at,
    result.result_payload,
    artifact.sha256,
    'extraction-review-queue/1.0.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  where result.validation_status = 'needs_review'
  order by result.created_at asc, result.id asc
  limit page_size;
end;
$function$;

revoke all on function api.get_extraction_review_queue(integer)
  from public, anon;
grant execute on function api.get_extraction_review_queue(integer)
  to authenticated;

comment on function api.get_extraction_review_queue(integer) is
  'Fila interna de candidatos needs_review; exige revisor ativo cadastrado.';
