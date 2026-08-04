-- Perfis individuais da ALBA: preserva a página oficial separadamente da
-- listagem e só projeta uma foto HTTPS hospedada pela própria Assembleia.

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
  'deputado-estadual-profile-html',
  'html',
  'https://www.al.ba.gov.br/deputados/deputado-estadual/{id_alba}',
  'GET',
  12,
  30,
  true,
  '{
    "parser_version": "alba-deputado-profile/1.0.0",
    "privacy": "somente nome, URL do perfil e imagem oficial quando publicada",
    "rate_limit_delay_seconds": 5
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

drop function if exists api.get_state_representatives(integer);

create function api.get_state_representatives(
  page_size integer default 100
)
returns table (
  external_id text,
  display_name text,
  profile_url text,
  photo_url text,
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
    case
      when profile.payload ->> 'foto_url' ~ '^https://www\.al\.ba\.gov\.br/fserver/'
        then profile.payload ->> 'foto_url'
      else null
    end as photo_url,
    deputy.collected_at,
    'state-representatives/alba/1.1.0'::text
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
  left join lateral (
    select record.payload
    from raw.raw_records as record
    where record.record_type = 'alba_deputado_estadual_profile'
      and record.payload ->> 'id_alba' = deputy.external_id
    order by record.collected_at desc
    limit 1
  ) as profile on true
  order by deputy.display_name
  limit page_size;
end;
$function$;

revoke all on function api.get_state_representatives(integer) from public;
grant execute on function api.get_state_representatives(integer)
  to anon, authenticated;

comment on function api.get_state_representatives(integer) is
  'Composição estadual publicada pela ALBA; fotos vêm de páginas individuais preservadas e não criam vínculo automático com Barreiras.';
