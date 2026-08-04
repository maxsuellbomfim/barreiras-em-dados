-- ADR 0014: dossiês de representação com vínculo territorial explícito.
-- Fatia 1: deputados federais eleitos pela Bahia (API aberta da Câmara).
-- O bruto preserva a resposta oficial integralmente; a projeção pública
-- NUNCA expõe CPF (regra inegociável de minimização) e declara o vínculo
-- territorial de cada pessoa em vez de sugerir representação local.

-- Cada corredor de Storage é uma decisão explícita: a lista de prefixos
-- permitidos cresce por migration, nunca por acidente.
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
        'camara-federal/deputados/'
      ]
    )
  );

insert into audit.storage_workload_identities (
  slug,
  auth_user_id,
  bucket_id,
  object_prefix,
  can_select,
  can_insert,
  status,
  activated_at,
  metadata
)
values (
  'camara-federal-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'camara-federal/deputados/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object('purpose', 'camara_federal_raw_artifacts')
)
on conflict (auth_user_id, object_prefix) do nothing;

insert into source.data_sources (
  id,
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
  '00000000-0000-4000-8000-000000000006',
  'camara-federal',
  'Câmara dos Deputados',
  'Dados abertos de deputados federais, mandatos e atuação parlamentar.',
  'official',
  true,
  'https://www.camara.leg.br/',
  'https://dadosabertos.camara.leg.br/swagger/api.html',
  'active'
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

insert into source.source_endpoints (
  id,
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
  '00000000-0000-4000-8000-000000000108',
  '00000000-0000-4000-8000-000000000006',
  'deputados-api',
  'api',
  'https://dadosabertos.camara.leg.br/api/v2/deputados',
  'GET',
  60,
  45,
  true,
  '{
    "uf": "BA",
    "pagination": {"itens": 100},
    "observed_at": "2026-08-01",
    "privacy": "CPF preservado no bruto e nunca exposto na projeção"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create or replace function api.get_federal_representatives(
  page_size integer default 60
)
returns table (
  external_id text,
  display_name text,
  civil_name text,
  party text,
  state_code text,
  electoral_status text,
  mandate_status text,
  photo_url text,
  email text,
  birth_state text,
  birth_city text,
  education text,
  legislature integer,
  territorial_link text,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  select
    deputy.external_id,
    deputy.display_name,
    -- Nome civil só quando a fonte oficial o publica; nunca inferido.
    deputy.civil_name,
    deputy.party,
    deputy.state_code,
    deputy.electoral_status,
    deputy.mandate_status,
    deputy.photo_url,
    deputy.email,
    deputy.birth_state,
    deputy.birth_city,
    deputy.education,
    deputy.legislature,
    -- ADR 0014: o vínculo é declarado, não presumido. Enquanto a votação
    -- nominal por município (TSE) não for coletada, o vínculo verificável
    -- é a eleição pelo estado.
    'eleito_pelo_estado'::text,
    deputy.collected_at,
    'federal-representatives/1.0.0'::text
  from (
    select distinct on (record.payload ->> 'id')
      record.payload ->> 'id' as external_id,
      coalesce(
        record.payload #>> '{ultimoStatus,nomeEleitoral}',
        record.payload ->> 'nome'
      ) as display_name,
      record.payload ->> 'nomeCivil' as civil_name,
      coalesce(
        record.payload #>> '{ultimoStatus,siglaPartido}',
        record.payload ->> 'siglaPartido'
      ) as party,
      coalesce(
        record.payload #>> '{ultimoStatus,siglaUf}',
        record.payload ->> 'siglaUf'
      ) as state_code,
      record.payload #>> '{ultimoStatus,condicaoEleitoral}'
        as electoral_status,
      record.payload #>> '{ultimoStatus,situacao}' as mandate_status,
      coalesce(
        record.payload #>> '{ultimoStatus,urlFoto}',
        record.payload ->> 'urlFoto'
      ) as photo_url,
      coalesce(
        record.payload #>> '{ultimoStatus,email}',
        record.payload ->> 'email'
      ) as email,
      record.payload ->> 'ufNascimento' as birth_state,
      record.payload ->> 'municipioNascimento' as birth_city,
      record.payload ->> 'escolaridade' as education,
      case
        when coalesce(
          record.payload #>> '{ultimoStatus,idLegislatura}',
          record.payload ->> 'idLegislatura'
        ) ~ '^[0-9]+$'
        then coalesce(
          record.payload #>> '{ultimoStatus,idLegislatura}',
          record.payload ->> 'idLegislatura'
        )::int
      end as legislature,
      record.collected_at
    from raw.raw_records as record
    where record.record_type in (
        'camara_deputado',
        'camara_deputado_detalhe'
      )
      and record.payload ->> 'id' ~ '^[0-9]+$'
    -- O detalhe (mais rico) vence a listagem para a mesma pessoa.
    order by
      record.payload ->> 'id',
      (record.record_type = 'camara_deputado_detalhe') desc,
      record.collected_at desc
  ) as deputy
  order by deputy.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_federal_representatives(integer) from public;
grant execute on function api.get_federal_representatives(integer)
  to anon, authenticated;

comment on function api.get_federal_representatives(integer) is
  'Deputados federais eleitos pela Bahia; CPF nunca é projetado (ADR 0014).';
