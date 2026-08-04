-- ADR 0014: votação nominal municipal como vínculo territorial mensurável.
-- O recorte já é agregado por código de candidatura e turno pelo coletor;
-- nomes nunca são usados como chave e a fonte nacional integral não é exposta.

insert into source.data_sources (
  slug,
  name,
  description,
  authority_level,
  is_official,
  homepage_url,
  documentation_url,
  status
)
values (
  'tse',
  'Tribunal Superior Eleitoral',
  'Resultados eleitorais e votação nominal por município, preservados por pleito.',
  'official',
  true,
  'https://www.tse.jus.br/',
  'https://dadosabertos.tse.jus.br/',
  'active'
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

insert into source.source_endpoints (
  data_source_id,
  slug,
  endpoint_kind,
  base_url,
  http_method,
  rate_limit_per_minute,
  request_timeout_seconds,
  enabled,
  config
)
values (
  (select id from source.data_sources where slug = 'tse'),
  'votacao-munzona',
  'file',
  'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/',
  'GET',
  4,
  120,
  true,
  '{
    "municipality_code": "33634",
    "ibge_code": "2903201",
    "aggregation": "by_candidate_and_turn",
    "parser_version": "tse-votacao-munzona/1.0.0",
    "privacy": "publica somente recorte agregado de votação"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create or replace function api.get_tse_barreiras_votes(
  page_size integer default 200
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
begin
  if page_size < 1 or page_size > 500 then
    raise exception 'page_size deve estar entre 1 e 500'
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
    order by
      record.payload ->> 'ano',
      record.payload ->> 'sq_candidato',
      record.payload ->> 'turno',
      record.collected_at desc
  ) as candidate
  order by candidate.election_year desc, candidate.votes_in_barreiras desc,
    candidate.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_tse_barreiras_votes(integer) from public;
grant execute on function api.get_tse_barreiras_votes(integer)
  to anon, authenticated;

comment on function api.get_tse_barreiras_votes(integer) is
  'Votação nominal agregada por candidatura e turno em Barreiras; não é avaliação de mandato.';
