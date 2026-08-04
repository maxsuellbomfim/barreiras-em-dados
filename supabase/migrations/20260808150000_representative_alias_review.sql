-- Sugestões de aliases da autoria legislativa, sempre separadas da fonte.
-- A IA pode ordenar uma hipótese, mas não cria vínculo público nem altera o
-- nome publicado pela Câmara. Somente um revisor ativo pode aceitar a linha.

create schema if not exists political;

create table if not exists political.representative_alias_suggestions (
  id uuid primary key default gen_random_uuid(),
  source_kind text not null check (source_kind in ('municipal')),
  observed_name text not null check (length(btrim(observed_name)) between 1 and 200),
  source_record_keys text[] not null default '{}',
  item_count integer not null check (item_count > 0),
  candidates jsonb not null check (jsonb_typeof(candidates) = 'array'),
  decision text not null check (decision in ('match', 'ambiguous', 'no_match')),
  candidate_external_id text,
  alias_kind text not null check (
    alias_kind in ('ballot_name', 'nickname', 'case_variant', 'spacing_variant', 'other')
  ),
  confidence numeric(4,3) not null check (confidence between 0 and 1),
  rationale text not null check (length(btrim(rationale)) between 1 and 800),
  evidence jsonb not null default '[]'::jsonb
    check (jsonb_typeof(evidence) = 'array'),
  provider text not null check (length(btrim(provider)) between 1 and 80),
  model text not null check (length(btrim(model)) between 1 and 160),
  prompt_version text not null,
  validator_version text not null,
  raw_response text not null check (length(raw_response) between 1 and 20000),
  status text not null default 'pending' check (
    status in ('pending', 'accepted', 'rejected', 'needs_more_evidence')
  ),
  reviewed_by uuid,
  reviewed_at timestamptz,
  review_note text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  unique (source_kind, observed_name, prompt_version),
  check (decision = 'match' or candidate_external_id is null or decision = 'ambiguous'),
  check (status = 'pending' or reviewed_at is not null)
);

create table if not exists political.representative_aliases (
  id uuid primary key default gen_random_uuid(),
  source_kind text not null check (source_kind in ('municipal')),
  representative_external_id text not null,
  canonical_name text not null check (length(btrim(canonical_name)) between 1 and 200),
  alias_text text not null check (length(btrim(alias_text)) between 1 and 200),
  alias_kind text not null check (
    alias_kind in ('ballot_name', 'nickname', 'case_variant', 'spacing_variant', 'other')
  ),
  evidence_url text not null,
  evidence_note text not null,
  source_record_keys text[] not null default '{}',
  approved_by uuid not null,
  approved_at timestamptz not null default statement_timestamp(),
  active boolean not null default true,
  unique (source_kind, representative_external_id, alias_text)
);

create index if not exists representative_alias_suggestions_status_idx
  on political.representative_alias_suggestions (status, created_at);

create index if not exists representative_aliases_lookup_idx
  on political.representative_aliases (source_kind, alias_text)
  where active;

alter table political.representative_tse_crosswalk enable row level security;
alter table political.representative_tse_crosswalk force row level security;
revoke all on table political.representative_tse_crosswalk
  from public, anon, authenticated;

create policy representative_tse_crosswalk_worker_select
on political.representative_tse_crosswalk
for select to collector_worker
using (true);

create trigger representative_alias_suggestions_set_updated_at
before update on political.representative_alias_suggestions
for each row execute function audit.set_updated_at();

alter table political.representative_alias_suggestions enable row level security;
alter table political.representative_alias_suggestions force row level security;
alter table political.representative_aliases enable row level security;
alter table political.representative_aliases force row level security;

revoke all on table political.representative_alias_suggestions
  from public, anon, authenticated;
revoke all on table political.representative_aliases
  from public, anon, authenticated;

create policy representative_alias_suggestions_worker_select
on political.representative_alias_suggestions
for select to collector_worker
using (true);

create policy representative_alias_suggestions_worker_insert
on political.representative_alias_suggestions
for insert to collector_worker
with check (status = 'pending');

create policy representative_alias_suggestions_worker_update
on political.representative_alias_suggestions
for update to collector_worker
using (status = 'pending')
with check (status = 'pending');

create policy representative_aliases_worker_select
on political.representative_aliases
for select to collector_worker
using (active);

create or replace function api.get_representative_alias_suggestions(
  page_size integer default 50
)
returns table (
  id uuid,
  observed_name text,
  source_record_keys text[],
  item_count integer,
  candidates jsonb,
  decision text,
  candidate_external_id text,
  alias_kind text,
  confidence numeric,
  rationale text,
  evidence jsonb,
  provider text,
  model text,
  prompt_version text,
  status text,
  created_at timestamptz
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;

  return query
  select
    suggestion.id,
    suggestion.observed_name,
    suggestion.source_record_keys,
    suggestion.item_count,
    suggestion.candidates,
    suggestion.decision,
    suggestion.candidate_external_id,
    suggestion.alias_kind,
    suggestion.confidence,
    suggestion.rationale,
    suggestion.evidence,
    suggestion.provider,
    suggestion.model,
    suggestion.prompt_version,
    suggestion.status,
    suggestion.created_at
  from political.representative_alias_suggestions as suggestion
  where suggestion.status = 'pending'
  order by suggestion.created_at asc, suggestion.id asc
  limit page_size;
end;
$function$;

revoke all on function api.get_representative_alias_suggestions(integer)
  from public, anon;
grant execute on function api.get_representative_alias_suggestions(integer)
  to authenticated;

create or replace function api.review_representative_alias_suggestion(
  suggestion_id uuid,
  review_decision text,
  review_note text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid := (select auth.uid());
  suggestion political.representative_alias_suggestions%rowtype;
  selected_candidate jsonb;
  canonical_name text;
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if review_decision not in ('accepted', 'rejected', 'needs_more_evidence') then
    raise exception 'decisão de alias inválida' using errcode = '22023';
  end if;
  if review_decision <> 'accepted'
     and nullif(btrim(review_note), '') is null then
    raise exception 'rejeição ou solicitação de evidência exige justificativa'
      using errcode = '22023';
  end if;

  select * into suggestion
  from political.representative_alias_suggestions
  where id = suggestion_id
    and status = 'pending'
  for update;
  if not found then
    raise exception 'sugestão inexistente ou já revisada' using errcode = '42501';
  end if;

  if review_decision = 'accepted' then
    if suggestion.candidate_external_id is null
       or suggestion.decision <> 'match' then
      raise exception 'somente uma sugestão match pode ser aceita'
        using errcode = '22023';
    end if;
    select candidate into selected_candidate
    from jsonb_array_elements(suggestion.candidates) as candidate
    where candidate ->> 'representative_external_id'
      = suggestion.candidate_external_id
    limit 1;
    canonical_name := nullif(btrim(selected_candidate ->> 'canonical_name'), '');
    if canonical_name is null then
      raise exception 'candidato aceito não possui nome canônico'
        using errcode = '22023';
    end if;
    insert into political.representative_aliases (
      source_kind, representative_external_id, canonical_name, alias_text,
      alias_kind, evidence_url, evidence_note, source_record_keys, approved_by
    ) values (
      suggestion.source_kind,
      suggestion.candidate_external_id,
      canonical_name,
      suggestion.observed_name,
      suggestion.alias_kind,
      'https://cmbarreiras.ba.gov.br/vereadores',
      'Alias aceito por revisão humana a partir de sugestão assistida. '
        || suggestion.rationale,
      suggestion.source_record_keys,
      reviewer_uid
    )
    on conflict (source_kind, representative_external_id, alias_text)
    do update set
      alias_kind = excluded.alias_kind,
      evidence_note = excluded.evidence_note,
      source_record_keys = excluded.source_record_keys,
      approved_by = excluded.approved_by,
      approved_at = statement_timestamp(),
      active = true;
  end if;

  update political.representative_alias_suggestions
  set status = review_decision,
      reviewed_by = reviewer_uid,
      reviewed_at = statement_timestamp(),
      review_note = nullif(btrim(review_note), ''),
      updated_at = statement_timestamp()
  where id = suggestion_id;
end;
$function$;

revoke all on function api.review_representative_alias_suggestion(uuid, text, text)
  from public, anon;
grant execute on function api.review_representative_alias_suggestion(uuid, text, text)
  to authenticated;

comment on table political.representative_alias_suggestions is
  'Hipóteses de alias geradas por IA para revisão; nunca são vínculos públicos automáticos.';
comment on table political.representative_aliases is
  'Aliases de representantes aceitos por revisor ativo, com evidência e trilha de auditoria.';
