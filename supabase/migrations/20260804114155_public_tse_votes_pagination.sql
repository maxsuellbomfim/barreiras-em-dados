-- Paginação determinística para o recorte municipal de votação do TSE.
-- A função legada continua disponível para consumidores antigos; o portal usa
-- esta função para não truncar silenciosamente históricos com mais de 500 linhas.

create or replace function api.get_tse_barreiras_votes_page(
  page_size integer default 200,
  page_offset integer default 0,
  election_year_filter integer default null,
  office_filter text default null
)
returns table (
  election_year integer,
  turn_number integer,
  office text,
  candidate_id text,
  candidate_number text,
  display_name text,
  ballot_name text,
  party text,
  situation text,
  votes_in_barreiras integer,
  zones integer,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  normalized_office text := nullif(btrim(office_filter), '');
begin
  if page_size < 1 or page_size > 500 then
    raise exception 'page_size deve estar entre 1 e 500'
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

  return query
  select
    candidate.election_year,
    candidate.turn_number,
    candidate.office,
    candidate.candidate_id,
    candidate.candidate_number,
    candidate.display_name,
    candidate.ballot_name,
    candidate.party,
    candidate.situation,
    candidate.votes_in_barreiras,
    candidate.zones,
    candidate.collected_at,
    'tse-votes-barreiras/1.0.0'::text
  from (
    select distinct on (
      record.payload ->> 'ano',
      record.payload ->> 'sq_candidato',
      record.payload ->> 'turno'
    )
      (record.payload ->> 'ano')::integer as election_year,
      (record.payload ->> 'turno')::integer as turn_number,
      btrim(record.payload ->> 'cargo') as office,
      record.payload ->> 'sq_candidato' as candidate_id,
      record.payload ->> 'numero' as candidate_number,
      btrim(record.payload ->> 'nome') as display_name,
      btrim(record.payload ->> 'nome_urna') as ballot_name,
      btrim(record.payload ->> 'partido') as party,
      btrim(record.payload ->> 'situacao') as situation,
      (record.payload ->> 'votos_em_barreiras')::integer as votes_in_barreiras,
      (record.payload ->> 'zonas')::integer as zones,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'tse_votacao_barreiras'
      and record.payload ->> 'ano' ~ '^[0-9]{4}$'
      and record.payload ->> 'turno' ~ '^[0-9]+$'
      and record.payload ->> 'sq_candidato' is not null
      and record.payload ->> 'sq_candidato' <> ''
      and record.payload ->> 'votos_em_barreiras' ~ '^[0-9]+$'
      and record.payload ->> 'zonas' ~ '^[0-9]+$'
      and (
        election_year_filter is null
        or (record.payload ->> 'ano')::integer = election_year_filter
      )
      and (
        normalized_office is null
        or btrim(record.payload ->> 'cargo') = normalized_office
      )
    order by
      record.payload ->> 'ano',
      record.payload ->> 'sq_candidato',
      record.payload ->> 'turno',
      record.collected_at desc
  ) as candidate
  order by candidate.election_year desc, candidate.votes_in_barreiras desc,
    candidate.display_name
  limit page_size
  offset page_offset;
end;
$function$;

revoke all on function api.get_tse_barreiras_votes_page(integer, integer, integer, text)
  from public;
grant execute on function api.get_tse_barreiras_votes_page(integer, integer, integer, text)
  to anon, authenticated;

comment on function api.get_tse_barreiras_votes_page(integer, integer, integer, text) is
  'Recorte municipal de votação nominal do TSE com paginação e filtros determinísticos; não é avaliação de mandato.';
