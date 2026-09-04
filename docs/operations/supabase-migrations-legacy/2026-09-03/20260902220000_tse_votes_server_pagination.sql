-- Estudo territorial do TSE em uma resposta limitada. As contagens, os grupos
-- do gráfico e os filtros são calculados sobre o recorte completo; somente os
-- registros visíveis da página atravessam a API pública.

create or replace function api.get_tse_barreiras_votes_study(
  page_size integer default 50,
  page_offset integer default 0,
  election_year_filter integer default null,
  use_latest_year boolean default true,
  office_filter text default null,
  turn_filter integer default null,
  outcome_filter text default null,
  query_filter text default null
)
returns table (
  items jsonb,
  total_count bigint,
  catalog_count bigint,
  elected_count bigint,
  votes_total bigint,
  groups jsonb,
  available_years integer[],
  available_offices text[],
  available_turns integer[],
  effective_year integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  normalized_office text := nullif(btrim(office_filter), '');
  normalized_outcome text := nullif(btrim(outcome_filter), '');
  normalized_query text := nullif(
    translate(
      lower(btrim(query_filter)),
      'áàâãäéèêëíìîïóòôõöúùûüç',
      'aaaaaeeeeiiiiooooouuuuc'
    ),
    ''
  );
begin
  if page_size < 1 or page_size > 50 then
    raise exception 'page_size deve estar entre 1 e 50'
      using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset deve estar entre 0 e 100000'
      using errcode = '22023';
  end if;
  if election_year_filter is not null
     and (election_year_filter < 1900 or election_year_filter > 2100) then
    raise exception 'election_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;
  if use_latest_year is null then
    raise exception 'use_latest_year não pode ser nulo'
      using errcode = '22023';
  end if;
  if turn_filter is not null and (turn_filter < 1 or turn_filter > 3) then
    raise exception 'turn_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;
  if normalized_outcome is not null
     and normalized_outcome not in (
       'elected', 'alternate', 'not_elected', 'other', 'unknown'
     ) then
    raise exception 'outcome_filter inválido'
      using errcode = '22023';
  end if;
  if query_filter is not null and length(query_filter) > 100 then
    raise exception 'query_filter excede 100 caracteres'
      using errcode = '22023';
  end if;

  return query
  with latest as materialized (
    select distinct on (record.source_record_key)
      record.payload,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'tse_votacao_barreiras'
      and record.source_record_key is not null
      and record.payload ->> 'ano' ~ '^[0-9]{4}$'
      and record.payload ->> 'turno' ~ '^[0-9]+$'
      and nullif(record.payload ->> 'sq_candidato', '') is not null
      and record.payload ->> 'votos_em_barreiras' ~ '^[0-9]+$'
      and record.payload ->> 'zonas' ~ '^[0-9]+$'
    order by record.source_record_key, record.collected_at desc, record.id desc
  ),
  candidates as materialized (
    select
      (latest.payload ->> 'ano')::integer as election_year,
      (latest.payload ->> 'turno')::integer as turn_number,
      nullif(btrim(latest.payload ->> 'cargo'), '') as office,
      latest.payload ->> 'sq_candidato' as candidate_id,
      nullif(btrim(latest.payload ->> 'numero'), '') as candidate_number,
      nullif(btrim(latest.payload ->> 'nome'), '') as display_name,
      nullif(btrim(latest.payload ->> 'nome_urna'), '') as ballot_name,
      nullif(btrim(latest.payload ->> 'partido'), '') as party,
      nullif(btrim(latest.payload ->> 'situacao'), '') as situation,
      (latest.payload ->> 'votos_em_barreiras')::integer as votes_in_barreiras,
      (latest.payload ->> 'zonas')::integer as zones,
      latest.collected_at,
      case
        when nullif(btrim(latest.payload ->> 'situacao'), '') is null
          then 'unknown'
        when translate(lower(btrim(latest.payload ->> 'situacao')),
          'áàâãäéèêëíìîïóòôõöúùûüç',
          'aaaaaeeeeiiiiooooouuuuc') = 'nao eleito'
          then 'not_elected'
        when translate(lower(btrim(latest.payload ->> 'situacao')),
          'áàâãäéèêëíìîïóòôõöúùûüç',
          'aaaaaeeeeiiiiooooouuuuc') = 'suplente'
          then 'alternate'
        when translate(lower(btrim(latest.payload ->> 'situacao')),
          'áàâãäéèêëíìîïóòôõöúùûüç',
          'aaaaaeeeeiiiiooooouuuuc') = 'eleito'
          or translate(lower(btrim(latest.payload ->> 'situacao')),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc') like 'eleito por %'
          then 'elected'
        else 'other'
      end as outcome
    from latest
  ),
  parameters as (
    select case
      when election_year_filter is not null then election_year_filter
      when use_latest_year then (select max(c.election_year) from candidates as c)
      else null
    end as selected_year
  ),
  filtered as materialized (
    select candidate.*
    from candidates as candidate
    cross join parameters
    where (
        parameters.selected_year is null
        or candidate.election_year = parameters.selected_year
      )
      and (
        normalized_office is null
        or candidate.office = normalized_office
      )
      and (
        turn_filter is null
        or candidate.turn_number = turn_filter
      )
      and (
        normalized_outcome is null
        or candidate.outcome = normalized_outcome
      )
      and (
        normalized_query is null
        or position(normalized_query in
          translate(
            lower(concat_ws(' ',
              candidate.ballot_name,
              candidate.display_name,
              candidate.party,
              candidate.candidate_number,
              candidate.candidate_id
            )),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
          )
        ) > 0
      )
  ),
  page_rows as (
    select filtered.*
    from filtered
    order by filtered.votes_in_barreiras desc,
      coalesce(filtered.ballot_name, filtered.display_name),
      filtered.candidate_id,
      filtered.turn_number
    limit page_size
    offset page_offset
  ),
  grouped as (
    select
      filtered.election_year,
      coalesce(filtered.office, 'Cargo não informado') as office,
      filtered.turn_number,
      count(*)::integer as candidates,
      sum(filtered.votes_in_barreiras)::bigint as votes
    from filtered
    group by filtered.election_year, filtered.office, filtered.turn_number
  )
  select
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'election_year', page_rows.election_year,
          'turn_number', page_rows.turn_number,
          'office', page_rows.office,
          'candidate_id', page_rows.candidate_id,
          'candidate_number', page_rows.candidate_number,
          'display_name', page_rows.display_name,
          'ballot_name', page_rows.ballot_name,
          'party', page_rows.party,
          'situation', page_rows.situation,
          'votes_in_barreiras', page_rows.votes_in_barreiras,
          'zones', page_rows.zones,
          'collected_at', page_rows.collected_at,
          'methodology_version', 'tse-votes-barreiras/1.0.0'
        )
        order by page_rows.votes_in_barreiras desc,
          coalesce(page_rows.ballot_name, page_rows.display_name),
          page_rows.candidate_id,
          page_rows.turn_number
      )
      from page_rows
    ), '[]'::jsonb) as items,
    (select count(*) from filtered) as total_count,
    (select count(*) from candidates) as catalog_count,
    (select count(*) from filtered where filtered.outcome = 'elected')
      as elected_count,
    case when turn_filter is null then null else
      (select coalesce(sum(filtered.votes_in_barreiras), 0) from filtered)
    end as votes_total,
    coalesce((
      select jsonb_agg(
        jsonb_build_object(
          'year', grouped.election_year,
          'office', grouped.office,
          'turn', grouped.turn_number,
          'candidates', grouped.candidates,
          'votes', grouped.votes
        )
        order by grouped.election_year desc, grouped.office, grouped.turn_number
      )
      from grouped
    ), '[]'::jsonb) as groups,
    coalesce((
      select array_agg(distinct candidate.election_year order by candidate.election_year desc)
      from candidates as candidate
    ), '{}'::integer[]) as available_years,
    coalesce((
      select array_agg(distinct candidate.office order by candidate.office)
      from candidates as candidate
      where candidate.office is not null
    ), '{}'::text[]) as available_offices,
    coalesce((
      select array_agg(distinct candidate.turn_number order by candidate.turn_number)
      from candidates as candidate
    ), '{}'::integer[]) as available_turns,
    (select parameters.selected_year from parameters) as effective_year,
    'tse-votes-study/1.0.0'::text as methodology_version;
end;
$function$;

revoke all on function api.get_tse_barreiras_votes_study(
  integer, integer, integer, boolean, text, integer, text, text
) from public;
grant execute on function api.get_tse_barreiras_votes_study(
  integer, integer, integer, boolean, text, integer, text, text
) to anon, authenticated;

comment on function api.get_tse_barreiras_votes_study(
  integer, integer, integer, boolean, text, integer, text, text
) is
  'Estudo municipal do TSE paginado no servidor; grupos e contagens respeitam eleição, cargo, turno e situação sem somar turnos por padrão.';
