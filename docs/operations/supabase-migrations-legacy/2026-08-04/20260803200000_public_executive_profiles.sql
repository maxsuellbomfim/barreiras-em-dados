-- Cadastro público do prefeito, vice e responsáveis pelas secretarias.
-- A projeção nasce de páginas oficiais preservadas em raw.raw_records;
-- nenhum nome é publicado sem relação com o artefato bruto correspondente.

insert into source.data_sources (
  slug, name, description, authority_level, is_official, homepage_url,
  documentation_url, status
)
values (
  'prefeitura-barreiras',
  'Prefeitura Municipal de Barreiras',
  'Páginas oficiais de prefeito, vice-prefeito e secretarias municipais.',
  'official', true,
  'https://barreiras.ba.gov.br/',
  'https://barreiras.ba.gov.br/prefeito-e-vice/',
  'active'
)
on conflict (slug) do update set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  (select id from source.data_sources where slug = 'prefeitura-barreiras'),
  'executive-pages-html',
  'html',
  'https://barreiras.ba.gov.br/prefeito-e-vice/',
  'GET', 12, 30, true,
  '{
    "parser_version": "barreiras-executive-pages/1.0.0",
    "privacy": "nome, função, secretaria, foto oficial e URL pública",
    "publication": "projeção pública somente de registros brutos preservados"
  }'::jsonb
)
on conflict (data_source_id, slug) do update set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create or replace function api.get_executive_profiles(
  page_size integer default 100
)
returns table (
  profile_key text,
  role text,
  department_name text,
  display_name text,
  profile_url text,
  photo_url text,
  source_excerpt text,
  collected_at timestamptz,
  source_url text,
  artifact_sha256 text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;

  return query
  select
    profile.profile_key,
    profile.role,
    profile.department_name,
    profile.display_name,
    profile.profile_url,
    profile.photo_url,
    profile.source_excerpt,
    profile.collected_at,
    profile.source_url,
    profile.artifact_sha256,
    'executive-profiles/barreiras/1.0.0'::text
  from (
    select distinct on (record.payload ->> 'profile_key')
      record.payload ->> 'profile_key' as profile_key,
      record.payload ->> 'role' as role,
      record.payload ->> 'department_name' as department_name,
      btrim(record.payload ->> 'display_name') as display_name,
      record.payload ->> 'profile_url' as profile_url,
      record.payload ->> 'photo_url' as photo_url,
      record.payload ->> 'source_excerpt' as source_excerpt,
      record.collected_at,
      artifact.source_url,
      artifact.sha256 as artifact_sha256
    from raw.raw_records as record
    join raw.raw_artifacts as artifact on artifact.id = record.raw_artifact_id
    where record.record_type = 'barreiras_executive_profile'
      and length(btrim(record.payload ->> 'profile_key')) > 0
      and record.payload ->> 'role' in ('prefeito', 'vice-prefeito', 'secretario')
      and length(btrim(record.payload ->> 'display_name')) > 0
      and record.payload ->> 'profile_url' ~ '^https://barreiras\.ba\.gov\.br/'
    order by record.payload ->> 'profile_key', record.collected_at desc, record.id desc
  ) as profile
  order by
    case profile.role
      when 'prefeito' then 1
      when 'vice-prefeito' then 2
      else 3
    end,
    profile.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_executive_profiles(integer) from public;
grant execute on function api.get_executive_profiles(integer) to anon, authenticated;

comment on function api.get_executive_profiles(integer) is
  'Perfis do Executivo municipal extraídos de páginas oficiais preservadas; não é cadastro de folha salarial.';
