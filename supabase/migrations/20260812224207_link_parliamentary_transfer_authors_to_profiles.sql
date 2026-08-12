-- Associa autores individuais publicados pelo Transferegov a perfis oficiais
-- somente por crosswalk curado e sustentado por identificadores oficiais.
-- Nenhuma aproximacao de nome acontece durante a consulta publica.

create table political.parliamentary_transfer_author_crosswalk (
  author_kind text not null check (author_kind = 'person'),
  author_key text not null check (
    author_key = lower(btrim(author_key))
    and length(author_key) between 2 and 200
  ),
  official_author_name text not null
    check (length(btrim(official_author_name)) between 2 and 200),
  representative_source_kind text not null
    check (representative_source_kind in ('federal', 'state')),
  representative_external_id text not null
    check (length(btrim(representative_external_id)) between 1 and 100),
  representative_profile_url text not null
    check (representative_profile_url ~ '^https://'),
  identity_evidence_url text not null
    check (identity_evidence_url ~ '^https://'),
  identity_evidence_note text not null
    check (length(btrim(identity_evidence_note)) between 20 and 2000),
  match_method text not null check (
    match_method = 'approved_official_profile_and_tse_crosswalk'
  ),
  review_status text not null default 'approved'
    check (review_status in ('pending', 'approved', 'rejected')),
  methodology_version text not null
    default 'parliamentary-transfer-author-crosswalk/1.0.0',
  approved_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  primary key (author_kind, author_key),
  check (review_status <> 'approved' or approved_at is not null)
);

create index parliamentary_transfer_author_crosswalk_profile_idx
  on political.parliamentary_transfer_author_crosswalk (
    representative_source_kind,
    representative_external_id
  )
  where review_status = 'approved';

create trigger parliamentary_transfer_author_crosswalk_set_updated_at
before update on political.parliamentary_transfer_author_crosswalk
for each row execute function audit.set_updated_at();

alter table political.parliamentary_transfer_author_crosswalk
  enable row level security;
alter table political.parliamentary_transfer_author_crosswalk
  force row level security;

revoke all on table political.parliamentary_transfer_author_crosswalk
  from public, anon, authenticated;

insert into political.parliamentary_transfer_author_crosswalk (
  author_kind,
  author_key,
  official_author_name,
  representative_source_kind,
  representative_external_id,
  representative_profile_url,
  identity_evidence_url,
  identity_evidence_note,
  match_method,
  review_status,
  approved_at
)
select
  'person',
  'ricardo maia',
  'RICARDO MAIA',
  crosswalk.source_kind,
  crosswalk.representative_external_id,
  'https://www.camara.leg.br/deputados/220694',
  crosswalk.evidence_url,
  'O perfil oficial da Camara 220694 publica Ricardo Maia e o crosswalk TSE '
    || 'aprovado liga esse perfil a candidatura 50001614047. O Transferegov '
    || 'publica RICARDO MAIA como autor individual da emenda.',
  'approved_official_profile_and_tse_crosswalk',
  'approved',
  statement_timestamp()
from political.representative_tse_crosswalk as crosswalk
where crosswalk.source_kind = 'federal'
  and crosswalk.representative_external_id = '220694'
  and crosswalk.election_year = 2022
  and crosswalk.office = 'Deputado Federal'
  and crosswalk.candidate_id = '50001614047'
  and crosswalk.review_status = 'approved'
on conflict (author_kind, author_key) do update set
  official_author_name = excluded.official_author_name,
  representative_source_kind = excluded.representative_source_kind,
  representative_external_id = excluded.representative_external_id,
  representative_profile_url = excluded.representative_profile_url,
  identity_evidence_url = excluded.identity_evidence_url,
  identity_evidence_note = excluded.identity_evidence_note,
  match_method = excluded.match_method,
  review_status = excluded.review_status,
  methodology_version = excluded.methodology_version,
  approved_at = excluded.approved_at,
  updated_at = statement_timestamp();

drop function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
);

create function api.get_public_parliamentary_transfer_ranking(
  author_scope text default 'person',
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_kind text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  amendment_count integer,
  destination_amount numeric(20,2),
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  fully_paid_amendment_count integer,
  first_year smallint,
  last_year smallint,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if author_scope not in ('person', 'collective') then
    raise exception 'author_scope deve ser person ou collective'
      using errcode = '22023';
  end if;
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      transfer.author_key,
      coalesce(
        max(transfer.author_name) filter (
          where transfer.author_name = upper(transfer.author_name)
        ),
        max(transfer.author_name)
      ) as author_name,
      transfer.author_kind,
      count(*)::integer as amendment_count,
      sum(transfer.destination_amount)::numeric(20,2) as destination_amount,
      sum(transfer.committed_amount)::numeric(20,2) as committed_amount,
      sum(transfer.paid_amount)::numeric(20,2) as paid_amount,
      count(*) filter (
        where transfer.paid_amount is not null
          and transfer.destination_amount is not null
          and transfer.paid_amount >= transfer.destination_amount
      )::integer as fully_paid_amendment_count,
      min(transfer.fiscal_year)::smallint as first_year,
      max(transfer.fiscal_year)::smallint as last_year
    from territory.parliamentary_transfers as transfer
    where (fiscal_year_filter is null or transfer.fiscal_year = fiscal_year_filter)
      and (
        (author_scope = 'person' and transfer.author_kind = 'person')
        or
        (author_scope = 'collective' and transfer.author_kind in (
          'commission', 'bench', 'collective'
        ))
      )
    group by transfer.author_key, transfer.author_kind
  ), linked as (
    select
      grouped.*,
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      case
        when grouped.author_kind <> 'person' then 'not_applicable_collective'
        when crosswalk.author_key is not null then 'approved_official_crosswalk'
        else 'not_linked'
      end as association_status
    from grouped
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = grouped.author_kind
      and crosswalk.author_key = grouped.author_key
      and crosswalk.review_status = 'approved'
  ), ranked as (
    select
      row_number() over (
        order by
          linked.paid_amount desc nulls last,
          linked.destination_amount desc,
          linked.author_name
      )::integer as rank_position,
      linked.*
    from linked
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_kind,
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    ranked.association_status,
    ranked.amendment_count,
    ranked.destination_amount,
    ranked.committed_amount,
    ranked.paid_amount,
    ranked.fully_paid_amendment_count,
    ranked.first_year,
    ranked.last_year,
    'parliamentary-transfer-ranking/1.1.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$function$;

revoke all on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) from public;
grant execute on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) to anon, authenticated;

comment on table political.parliamentary_transfer_author_crosswalk is
  'Associacoes revisadas entre autoria individual no Transferegov e perfil oficial; nunca usa aproximacao em consulta.';
comment on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) is
  'Ranking objetivo de emendas com perfil somente quando existe crosswalk oficial aprovado.';

notify pgrst, 'reload schema';
