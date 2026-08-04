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
        'camara-municipal/vereadores/'
      ]
    )
  );

insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix,
  can_select, can_insert, status, activated_at, metadata
)
values (
  'camara-municipal-collector',
  '1575c740-fcff-4b1a-89a9-e8e5a314880a',
  'raw-artifacts',
  'camara-municipal/vereadores/',
  true, true, 'active', statement_timestamp(),
  jsonb_build_object('purpose', 'camara_municipal_raw_artifacts')
)
on conflict (auth_user_id, object_prefix) do nothing;

insert into source.data_sources (
  id, slug, name, description, authority_level, is_official,
  homepage_url, documentation_url, status
)
values (
  '00000000-0000-4000-8000-000000000007',
  'camara-municipal-barreiras',
  'Camara Municipal de Barreiras',
  'Composicao da casa legislativa municipal publicada no portal oficial.',
  'official', true,
  'https://cmbarreiras.ba.gov.br/',
  'https://cmbarreiras.ba.gov.br/vereadores',
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
  '00000000-0000-4000-8000-000000000109',
  '00000000-0000-4000-8000-000000000007',
  'vereadores-html',
  'html',
  'https://cmbarreiras.ba.gov.br/vereadores',
  'GET', 10, 30, true,
  '{"observed_at": "2026-08-01", "note": "portal WordPress renderizado no servidor; duas marcacoes de rotulo (strong e b)", "discovery": "docs/reviews/STAGE_6_REPRESENTATION_SOURCES.md"}'::jsonb
)
on conflict (data_source_id, slug) do update
set base_url = excluded.base_url,
    rate_limit_per_minute = excluded.rate_limit_per_minute,
    request_timeout_seconds = excluded.request_timeout_seconds,
    enabled = excluded.enabled,
    config = excluded.config;

create or replace function api.get_municipal_councillors(
  page_size integer default 40
)
returns table (
  councillor_id text,
  display_name text,
  party text,
  mandates text,
  main_agenda text,
  biography text,
  photo_url text,
  source_url text,
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
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;

  return query
  select
    councillor.source_record_key,
    councillor.nome,
    councillor.partido,
    councillor.mandatos,
    councillor.bandeira,
    councillor.biografia,
    councillor.foto_url,
    'https://cmbarreiras.ba.gov.br/vereadores'::text,
    councillor.collected_at,
    'municipal-councillors/1.0.0'::text
  from (
    select distinct on (record.source_record_key)
      record.source_record_key,
      record.payload ->> 'nome' as nome,
      record.payload ->> 'partido' as partido,
      record.payload ->> 'mandatos' as mandatos,
      record.payload ->> 'bandeira' as bandeira,
      record.payload ->> 'biografia' as biografia,
      record.payload ->> 'foto_url' as foto_url,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'cm_barreiras_vereador'
      and record.payload ->> 'nome' is not null
    order by record.source_record_key, record.collected_at desc
  ) as councillor
  order by councillor.nome
  limit page_size;
end;
$function$;

revoke all on function api.get_municipal_councillors(integer) from public;
grant execute on function api.get_municipal_councillors(integer)
  to anon, authenticated;

comment on function api.get_municipal_councillors(integer) is
  'Vereadores de Barreiras publicados no portal oficial da Camara (ADR 0014).';;
