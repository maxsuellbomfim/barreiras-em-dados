-- Cadastro separado para ex-vereadores e outros mandatos históricos.
-- Nomes históricos podem ser confirmados editorialmente sem serem ligados a
-- um perfil eleitoral atual antes de existir uma fonte oficial suficiente.

create schema if not exists political;

create table if not exists political.historical_representatives (
  id uuid primary key default gen_random_uuid(),
  jurisdiction text not null default 'Barreiras-BA'
    check (length(btrim(jurisdiction)) between 1 and 120),
  canonical_name text not null
    check (length(btrim(canonical_name)) between 1 and 200),
  role_title text not null default 'Vereador'
    check (length(btrim(role_title)) between 1 and 120),
  mandate_status text not null default 'former'
    check (mandate_status in ('former', 'current', 'unknown')),
  term_start_date date,
  term_end_date date,
  editorial_status text not null default 'source_pending'
    check (editorial_status in ('draft', 'source_pending', 'approved', 'withdrawn')),
  source_url text,
  source_record_keys text[] not null default '{}',
  evidence_note text not null
    check (length(btrim(evidence_note)) between 1 and 2000),
  methodology_version text not null default 'historical-representatives/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  unique (jurisdiction, canonical_name),
  check (
    term_end_date is null
    or term_start_date is null
    or term_end_date >= term_start_date
  ),
  check (
    editorial_status <> 'approved'
    or nullif(btrim(source_url), '') is not null
  ),
  check (
    source_url is null
    or source_url ~ '^https://'
  )
);

create table if not exists political.historical_representative_aliases (
  id uuid primary key default gen_random_uuid(),
  historical_representative_id uuid not null
    references political.historical_representatives(id) on delete cascade,
  alias_text text not null
    check (length(btrim(alias_text)) between 1 and 200),
  alias_kind text not null default 'name_variant'
    check (alias_kind in ('name_variant', 'ballot_name', 'nickname', 'editorial_prefix', 'other')),
  source_suggestion_id uuid
    references political.representative_alias_suggestions(id) on delete set null,
  evidence_url text,
  evidence_note text not null
    check (length(btrim(evidence_note)) between 1 and 2000),
  source_record_keys text[] not null default '{}',
  approved_by uuid,
  approved_at timestamptz,
  active boolean not null default true,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  unique (historical_representative_id, alias_text),
  check (
    evidence_url is null
    or evidence_url ~ '^https://'
  ),
  check (active = false or approved_by is not null),
  check (active = false or approved_at is not null)
);

alter table political.representative_alias_suggestions
  add column if not exists historical_representative_id uuid
    references political.historical_representatives(id) on delete set null;

create index if not exists historical_representatives_status_idx
  on political.historical_representatives (editorial_status, mandate_status, canonical_name);

create index if not exists historical_representative_aliases_lookup_idx
  on political.historical_representative_aliases (alias_text)
  where active;

create index if not exists representative_alias_suggestions_historical_idx
  on political.representative_alias_suggestions (historical_representative_id)
  where historical_representative_id is not null;

create trigger historical_representatives_set_updated_at
before update on political.historical_representatives
for each row execute function audit.set_updated_at();

create trigger historical_representative_aliases_set_updated_at
before update on political.historical_representative_aliases
for each row execute function audit.set_updated_at();

alter table political.historical_representatives enable row level security;
alter table political.historical_representatives force row level security;
alter table political.historical_representative_aliases enable row level security;
alter table political.historical_representative_aliases force row level security;

revoke all on table political.historical_representatives
  from public, anon, authenticated;
revoke all on table political.historical_representative_aliases
  from public, anon, authenticated;

create policy historical_representatives_worker_select
on political.historical_representatives
for select to collector_worker
using (true);

create policy historical_representative_aliases_worker_select
on political.historical_representative_aliases
for select to collector_worker
using (active);

create or replace function api.get_historical_representatives(
  page_size integer default 100
)
returns table (
  id uuid,
  jurisdiction text,
  canonical_name text,
  role_title text,
  mandate_status text,
  term_start_date date,
  term_end_date date,
  source_url text,
  evidence_note text,
  aliases jsonb,
  methodology_version text,
  updated_at timestamptz
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 300 then
    raise exception 'page_size deve estar entre 1 e 300' using errcode = '22023';
  end if;

  return query
  select
    historical.id,
    historical.jurisdiction,
    historical.canonical_name,
    historical.role_title,
    historical.mandate_status,
    historical.term_start_date,
    historical.term_end_date,
    historical.source_url,
    historical.evidence_note,
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'alias', alias_row.alias_text,
            'kind', alias_row.alias_kind,
            'evidence_url', alias_row.evidence_url
          )
          order by alias_row.alias_text
        )
        from political.historical_representative_aliases as alias_row
        where alias_row.historical_representative_id = historical.id
          and alias_row.active
      ),
      '[]'::jsonb
    ),
    historical.methodology_version,
    historical.updated_at
  from political.historical_representatives as historical
  where historical.editorial_status = 'approved'
  order by historical.canonical_name
  limit page_size;
end;
$function$;

revoke all on function api.get_historical_representatives(integer)
  from public;
grant execute on function api.get_historical_representatives(integer)
  to anon, authenticated;

comment on table political.historical_representatives is
  'Registro versionado de representantes históricos; somente linhas aprovadas com fonte oficial são públicas.';

comment on table political.historical_representative_aliases is
  'Variações históricas de nome ligadas a um representante histórico com evidência própria.';

comment on function api.get_historical_representatives(integer) is
  'Ex-vereadores e mandatos históricos aprovados editorialmente, sem misturá-los à legislatura atual.';
