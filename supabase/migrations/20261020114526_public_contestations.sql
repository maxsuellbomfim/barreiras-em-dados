begin;

-- Contestação anônima com protocolo (ADR 0099, política editorial). Substitui
-- as issues públicas do GitHub, que exigiam conta e expunham quem contestava.
-- A tabela não tem política de acesso: só as funções abaixo leem e gravam.
-- Texto e contato nunca são públicos; a consulta por protocolo mostra só a
-- página contestada, o estado e a resolução.
create table editorial.public_contestations (
  id uuid primary key default gen_random_uuid(),
  protocol text not null unique
    check (protocol ~ '^C-[0-9A-F]{10}$'),
  target_path text not null
    check (target_path ~ '^/[^\s]{0,299}$'),
  description text not null
    check (length(btrim(description)) between 10 and 4000),
  evidence_url text
    check (evidence_url is null or (evidence_url ~ '^https://' and length(evidence_url) <= 500)),
  contact text
    check (contact is null or length(contact) <= 200),
  status text not null default 'received'
    check (status in ('received', 'under_review', 'upheld', 'rejected', 'withdrawn')),
  resolution_note text
    check (resolution_note is null or length(btrim(resolution_note)) between 5 and 2000),
  resolved_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp()
);

create index public_contestations_created_idx
  on editorial.public_contestations (created_at desc);

alter table editorial.public_contestations enable row level security;
revoke all on editorial.public_contestations from public, anon, authenticated;

create or replace function api.submit_public_contestation(
  p_target_path text,
  p_description text,
  p_evidence_url text default null,
  p_contact text default null
)
returns table (protocol text)
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  clean_path text := btrim(coalesce(p_target_path, ''));
  clean_description text := btrim(coalesce(p_description, ''));
  clean_evidence text := nullif(btrim(coalesce(p_evidence_url, '')), '');
  clean_contact text := nullif(btrim(coalesce(p_contact, '')), '');
  existing text;
  new_protocol text;
begin
  if clean_path !~ '^/[^\s]{0,299}$' then
    raise exception 'informe a página contestada (começa com /)' using errcode = '22023';
  end if;
  if length(clean_description) not between 10 and 4000 then
    raise exception 'a descrição deve ter entre 10 e 4000 caracteres' using errcode = '22023';
  end if;
  if clean_evidence is not null and (clean_evidence !~ '^https://' or length(clean_evidence) > 500) then
    raise exception 'o link de evidência deve começar com https://' using errcode = '22023';
  end if;
  if clean_contact is not null and length(clean_contact) > 200 then
    raise exception 'contato muito longo' using errcode = '22023';
  end if;

  -- Reenvio idêntico no mesmo dia devolve o mesmo protocolo.
  select contestation.protocol into existing
  from editorial.public_contestations as contestation
  where contestation.target_path = clean_path
    and contestation.description = clean_description
    and contestation.created_at > statement_timestamp() - interval '1 day'
  limit 1;
  if existing is not null then
    return query select existing;
    return;
  end if;

  -- Limite global contra abuso, sem guardar IP (anonimato).
  if (
    select count(*) from editorial.public_contestations as recent
    where recent.created_at > statement_timestamp() - interval '1 hour'
  ) >= 60 then
    raise exception 'muitas contestações nesta hora; tente de novo mais tarde'
      using errcode = '53400';
  end if;

  loop
    new_protocol := 'C-' || upper(substr(md5(gen_random_uuid()::text), 1, 10));
    exit when not exists (
      select 1 from editorial.public_contestations as taken
      where taken.protocol = new_protocol
    );
  end loop;

  insert into editorial.public_contestations (
    protocol, target_path, description, evidence_url, contact
  ) values (
    new_protocol, clean_path, clean_description, clean_evidence, clean_contact
  );
  return query select new_protocol;
end;
$function$;

create or replace function api.get_public_contestation(p_protocol text)
returns table (
  protocol text,
  target_path text,
  status text,
  resolution_note text,
  created_at timestamptz,
  resolved_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $function$
  select contestation.protocol, contestation.target_path, contestation.status,
    contestation.resolution_note, contestation.created_at, contestation.resolved_at
  from editorial.public_contestations as contestation
  where contestation.protocol = upper(btrim(p_protocol));
$function$;

revoke all on function api.submit_public_contestation(text, text, text, text) from public;
grant execute on function api.submit_public_contestation(text, text, text, text) to anon, authenticated;
revoke all on function api.get_public_contestation(text) from public;
grant execute on function api.get_public_contestation(text) to anon, authenticated;

notify pgrst, 'reload schema';

commit;
