alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/'
      ]
    )
  );

insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix,
  can_select, can_insert, status, activated_at, metadata
)
values (
  'tse-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'tse/votacao/',
  true, true, 'active', statement_timestamp(),
  jsonb_build_object('purpose', 'tse_votacao_raw_artifacts')
)
on conflict (auth_user_id, object_prefix) do nothing;

insert into source.data_sources (
  id, slug, name, description, authority_level, is_official,
  homepage_url, documentation_url, status
)
values (
  '00000000-0000-4000-8000-000000000008',
  'tse',
  'Tribunal Superior Eleitoral',
  'Repositorio de dados eleitorais: votacao nominal por municipio e zona.',
  'official', true,
  'https://www.tse.jus.br/',
  'https://dadosabertos.tse.jus.br/',
  'active'
)
on conflict (slug) do update
set name = excluded.name,
    description = excluded.description,
    documentation_url = excluded.documentation_url,
    status = excluded.status;

insert into source.source_endpoints (
  id, data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  '00000000-0000-4000-8000-000000000110',
  '00000000-0000-4000-8000-000000000008',
  'votacao-munzona',
  'file',
  'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/',
  'GET', 5, 120, true,
  '{"municipio_tse": "33634", "uf": "BA", "observed_at": "2026-08-01", "licenca": "CC-BY", "nota": "pacote nacional; preservamos o recorte de Barreiras com hash do pacote e do CSV estadual"}'::jsonb
)
on conflict (data_source_id, slug) do update
set base_url = excluded.base_url,
    rate_limit_per_minute = excluded.rate_limit_per_minute,
    request_timeout_seconds = excluded.request_timeout_seconds,
    enabled = excluded.enabled,
    config = excluded.config;

create or replace function api.get_barreiras_election_results(
  filter_year integer default null,
  page_size integer default 100
)
returns table (
  candidacy_id text,
  election_year integer,
  turn integer,
  office text,
  candidate_name text,
  ballot_name text,
  party text,
  votes_in_barreiras integer,
  zones integer,
  outcome text,
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
    raise exception 'page_size deve estar entre 1 e 500' using errcode = '22023';
  end if;

  return query
  select
    vote.source_record_key,
    vote.ano,
    vote.turno,
    vote.cargo,
    vote.nome,
    vote.nome_urna,
    vote.partido,
    vote.votos,
    vote.zonas,
    vote.situacao,
    vote.collected_at,
    'barreiras-election-results/1.0.0'::text
  from (
    select distinct on (record.source_record_key)
      record.source_record_key,
      (record.payload ->> 'ano')::int as ano,
      (record.payload ->> 'turno')::int as turno,
      record.payload ->> 'cargo' as cargo,
      record.payload ->> 'nome' as nome,
      record.payload ->> 'nome_urna' as nome_urna,
      record.payload ->> 'partido' as partido,
      (record.payload ->> 'votos_em_barreiras')::int as votos,
      (record.payload ->> 'zonas')::int as zonas,
      record.payload ->> 'situacao' as situacao,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'tse_votacao_barreiras'
      and record.payload ->> 'votos_em_barreiras' ~ '^[0-9]+$'
      and (
        filter_year is null
        or (record.payload ->> 'ano')::int = filter_year
      )
    order by record.source_record_key, record.collected_at desc
  ) as vote
  order by vote.ano desc, vote.votos desc
  limit page_size;
end;
$function$;

revoke all on function api.get_barreiras_election_results(integer, integer)
  from public;
grant execute on function api.get_barreiras_election_results(integer, integer)
  to anon, authenticated;

comment on function api.get_barreiras_election_results(integer, integer) is
  'Votos recebidos em Barreiras por candidatura: o vinculo territorial mensuravel do ADR 0014.';;
