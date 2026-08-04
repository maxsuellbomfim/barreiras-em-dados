-- Primeira projeção legislativa da API de dados abertos da Câmara Municipal.
-- A fonte informa a lei e sua ementa, mas não deve ser usada para inferir
-- autoria individual quando esse vínculo não vier no registro oficial.

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
  'camara-barreiras-transparencia',
  'Portal da Transparência da Câmara Municipal de Barreiras',
  'API oficial de contratos, atos, documentos, RH e atividade legislativa.',
  'official',
  true,
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/',
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/dados-abertos/',
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
  (select id from source.data_sources where slug = 'camara-barreiras-transparencia'),
  'leis-api',
  'api',
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/api',
  'GET',
  10,
  30,
  true,
  '{
    "resource": "leis",
    "pagination": {"limit": 50, "offset": 0},
    "observed_fields": ["id_lei", "data", "tipo", "titulo", "ano_ref", "informacoes", "url", "ativo"]
  }'::jsonb
)
on conflict (data_source_id, slug) do update
set
  base_url = excluded.base_url,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create or replace function api.get_camara_laws(
  page_size integer default 200
)
returns table (
  law_id text,
  publication_date text,
  reference_year integer,
  law_type text,
  title text,
  summary text,
  source_url text,
  active boolean,
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
    law.law_id,
    law.publication_date,
    law.reference_year,
    law.law_type,
    law.title,
    law.summary,
    law.source_url,
    law.active,
    law.collected_at,
    'camara-laws/1.0.0'::text
  from (
    select distinct on (record.payload ->> 'id_lei')
      btrim(record.payload ->> 'id_lei') as law_id,
      nullif(btrim(record.payload ->> 'data'), '') as publication_date,
      case
        when record.payload ->> 'ano_ref' ~ '^[0-9]{4}$'
        then (record.payload ->> 'ano_ref')::integer
      end as reference_year,
      nullif(btrim(record.payload ->> 'tipo'), '') as law_type,
      nullif(btrim(record.payload ->> 'titulo'), '') as title,
      nullif(btrim(record.payload ->> 'informacoes'), '') as summary,
      case
        when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
      end as source_url,
      case
        when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'não', 'nao') then false
      end as active,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_leis'
      and length(btrim(record.payload ->> 'id_lei')) > 0
      and (
        length(btrim(record.payload ->> 'titulo')) > 0
        or length(btrim(record.payload ->> 'informacoes')) > 0
      )
    order by record.payload ->> 'id_lei', record.collected_at desc
  ) as law
  order by law.reference_year desc nulls last, law.publication_date desc nulls last,
    law.law_id
  limit page_size;
end;
$function$;

revoke all on function api.get_camara_laws(integer) from public;
grant execute on function api.get_camara_laws(integer)
  to anon, authenticated;

comment on function api.get_camara_laws(integer) is
  'Leis publicadas pela API da Câmara Municipal; autoria individual só aparece quando a fonte a informa.';
