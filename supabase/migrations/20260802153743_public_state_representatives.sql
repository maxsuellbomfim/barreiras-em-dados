-- ADR 0014: primeira projeção pública dos deputados estaduais da Bahia.
-- A fonte da ALBA é HTML e publica apenas identificador, nome e perfil na
-- listagem. Vínculo individual com Barreiras não é presumido nesta fatia.

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
  'alba',
  'Assembleia Legislativa da Bahia',
  'Composição publicada pela Assembleia Legislativa da Bahia em HTML.',
  'official',
  true,
  'https://www.al.ba.gov.br/',
  'https://www.al.ba.gov.br/deputados/deputados-estaduais',
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
  (select id from source.data_sources where slug = 'alba'),
  'deputados-estaduais-html',
  'html',
  'https://www.al.ba.gov.br/deputados/deputados-estaduais',
  'GET',
  12,
  30,
  true,
  '{
    "parser_version": "alba-deputados/1.0.0",
    "privacy": "somente identificador, nome e URL oficial do perfil",
    "territorial_link": "not_collected"
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create or replace function api.get_state_representatives(
  page_size integer default 100
)
returns table (
  external_id text,
  display_name text,
  profile_url text,
  collected_at timestamptz,
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
    deputy.external_id,
    deputy.display_name,
    deputy.profile_url,
    deputy.collected_at,
    'state-representatives/alba/1.0.0'::text
  from (
    select distinct on (record.payload ->> 'id_alba')
      record.payload ->> 'id_alba' as external_id,
      btrim(record.payload ->> 'nome') as display_name,
      record.payload ->> 'perfil_url' as profile_url,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'alba_deputado_estadual'
      and record.payload ->> 'id_alba' ~ '^[0-9]+$'
      and length(btrim(record.payload ->> 'nome')) > 0
      and record.payload ->> 'perfil_url' ~ '^https://www\.al\.ba\.gov\.br/deputados/deputado-estadual/[0-9]+$'
    order by
      record.payload ->> 'id_alba',
      record.collected_at desc
  ) as deputy
  order by deputy.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_state_representatives(integer) from public;
grant execute on function api.get_state_representatives(integer)
  to anon, authenticated;

comment on function api.get_state_representatives(integer) is
  'Composição estadual publicada pela ALBA; vínculo individual com Barreiras não é presumido.';
