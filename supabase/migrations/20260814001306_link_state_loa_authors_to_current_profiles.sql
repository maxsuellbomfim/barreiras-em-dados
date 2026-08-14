begin;

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
  methodology_version,
  approved_at
)
with candidates (
  author_key,
  official_author_name,
  representative_source_kind,
  representative_external_id,
  representative_profile_url,
  candidate_id,
  election_office
) as (
  values
    (
      'capitao alden',
      'Capitão Alden',
      'federal',
      '220690',
      'https://www.camara.leg.br/deputados/220690',
      '50001609344',
      'Deputado Federal'
    ),
    (
      'diego castro',
      'Diego Castro',
      'state',
      '932099',
      'https://www.al.ba.gov.br/deputados/deputado-estadual/932099',
      '50001609451',
      'Deputado Estadual'
    )
)
select
  'person',
  candidate.author_key,
  candidate.official_author_name,
  candidate.representative_source_kind,
  candidate.representative_external_id,
  candidate.representative_profile_url,
  crosswalk.evidence_url,
  'A autoria nominal publicada no anexo da LOA da Bahia coincide com a '
    || 'candidatura TSE de 2022 ja reconciliada com o perfil oficial atual '
    || candidate.representative_external_id
    || '. O perfil atual nao altera o contexto historico da autoria orcamentaria.',
  'approved_official_profile_and_tse_crosswalk',
  'approved',
  'parliamentary-transfer-author-crosswalk/1.1.0',
  statement_timestamp()
from candidates as candidate
join political.representative_tse_crosswalk as crosswalk
  on crosswalk.source_kind = candidate.representative_source_kind
  and crosswalk.representative_external_id = candidate.representative_external_id
  and crosswalk.election_year = 2022
  and crosswalk.office = candidate.election_office
  and crosswalk.candidate_id = candidate.candidate_id
  and crosswalk.review_status = 'approved'
on conflict (author_kind, author_key) do nothing;

drop function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
);

create function api.get_public_bahia_state_loa_amendment_ranking(
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_external_code text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  amendment_count integer,
  authorized_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  financial_stage text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite do ranking estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2022 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano do ranking estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      amendment.author_key,
      (array_agg(
        amendment.author_name
        order by amendment.fiscal_year desc, amendment.created_at desc
      ))[1] as author_name,
      (array_agg(
        amendment.author_external_code
        order by
          (amendment.author_external_code is not null) desc,
          amendment.fiscal_year desc,
          amendment.created_at desc
      ))[1] as author_external_code,
      count(*)::integer as amendment_count,
      sum(amendment.authorized_amount)::numeric(20,2) as authorized_amount,
      min(amendment.fiscal_year)::smallint as first_year,
      max(amendment.fiscal_year)::smallint as last_year
    from territory.bahia_state_loa_amendments as amendment
    where (
      fiscal_year_filter is null
      or amendment.fiscal_year = fiscal_year_filter
    )
    group by amendment.author_key
  ), linked as (
    select
      grouped.*,
      crosswalk.representative_source_kind,
      crosswalk.representative_external_id,
      crosswalk.representative_profile_url,
      case
        when crosswalk.author_key is not null
          then 'approved_official_crosswalk'
        else 'not_linked'
      end as association_status
    from grouped
    left join political.parliamentary_transfer_author_crosswalk as crosswalk
      on crosswalk.author_kind = 'person'
      and crosswalk.author_key = grouped.author_key
      and crosswalk.review_status = 'approved'
  ), ranked as (
    select
      row_number() over (
        order by linked.authorized_amount desc, linked.author_name
      )::integer as rank_position,
      linked.*
    from linked
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_external_code,
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    ranked.association_status,
    ranked.amendment_count,
    ranked.authorized_amount,
    ranked.first_year,
    ranked.last_year,
    'authorized'::text,
    'bahia-state-loa-amendment-ranking/1.2.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

revoke all on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) from public;
grant execute on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) to anon, authenticated;

comment on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) is
  'Ranking por valor autorizado na LOA; autoria historica e perfil oficial atual sao contextos distintos.';

notify pgrst, 'reload schema';

commit;
