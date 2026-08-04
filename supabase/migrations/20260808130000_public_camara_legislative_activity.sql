-- Projeção única de leis e indicações da Câmara.
-- A autoria só é exibida quando vier do registro oficial; não há fuzzy matching.

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  (select id from source.data_sources where slug = 'camara-barreiras-transparencia'),
  'indicacoes-api', 'api',
  'https://portaldatransparencia.cmbarreiras.ba.gov.br/api', 'GET',
  10, 30, true,
  '{"resource":"indicacoes","pagination":{"limit":50,"offset":0},"observed_fields":["id_indicacao","numero_protocolo","data_protocolo","data_aprovacao","titulo","autoria","situacao","informacoes","url","ativo"]}'::jsonb
)
on conflict (data_source_id, slug) do update set
  enabled = excluded.enabled,
  config = excluded.config,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds;

create or replace function api.get_camara_legislative_items(
  page_size integer default 500,
  item_kind_filter text default null,
  year_filter integer default null,
  author_filter text default null,
  query_filter text default null
)
returns table (
  item_id text,
  item_kind text,
  protocol_number text,
  publication_date text,
  reference_year integer,
  item_type text,
  title text,
  summary text,
  author_name text,
  situation text,
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
    raise exception 'page_size deve estar entre 1 e 500' using errcode = '22023';
  end if;
  if item_kind_filter is not null and item_kind_filter not in ('lei', 'indicacao') then
    raise exception 'item_kind_filter deve ser lei ou indicacao' using errcode = '22023';
  end if;
  if year_filter is not null and (year_filter < 1900 or year_filter > 2200) then
    raise exception 'year_filter fora do intervalo' using errcode = '22023';
  end if;

  return query
  with candidates as (
    select
      btrim(record.payload ->> 'id_lei') as item_id,
      'lei'::text as item_kind,
      null::text as protocol_number,
      case when record.payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        and record.payload ->> 'data' <> '0000-00-00' then record.payload ->> 'data' end as publication_date,
      case when record.payload ->> 'ano_ref' ~ '^[0-9]{4}$' then (record.payload ->> 'ano_ref')::integer
        when record.payload ->> 'data' ~ '^[0-9]{4}' then left(record.payload ->> 'data', 4)::integer end as reference_year,
      nullif(btrim(record.payload ->> 'tipo'), '') as item_type,
      nullif(btrim(record.payload ->> 'titulo'), '') as title,
      nullif(btrim(record.payload ->> 'informacoes'), '') as summary,
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor', record.payload ->> 'author')), '') as author_name,
      null::text as situation,
      case
        when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/')
      end as source_url,
      case
        when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false
      end as active,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_leis'
      and length(btrim(record.payload ->> 'id_lei')) > 0
      and (length(btrim(record.payload ->> 'titulo')) > 0 or length(btrim(record.payload ->> 'informacoes')) > 0)
    union all
    select
      btrim(record.payload ->> 'id_indicacao'),
      'indicacao'::text,
      nullif(btrim(record.payload ->> 'numero_protocolo'), ''),
      case
        when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_protocolo' <> '0000-00-00' then record.payload ->> 'data_protocolo'
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_aprovacao' <> '0000-00-00' then record.payload ->> 'data_aprovacao'
        when record.payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data' <> '0000-00-00' then record.payload ->> 'data'
      end,
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}' then left(record.payload ->> 'data_protocolo', 4)::integer
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}' then left(record.payload ->> 'data_aprovacao', 4)::integer end,
      nullif(btrim(record.payload ->> 'tipo'), ''),
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor')), ''),
      nullif(btrim(record.payload ->> 'situacao'), ''),
      case
        when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/')
      end,
      case
        when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false
      end,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_indicacoes'
      and length(btrim(record.payload ->> 'id_indicacao')) > 0
      and length(btrim(record.payload ->> 'informacoes')) > 0
  ), latest as (
    select distinct on (candidates.item_kind, candidates.item_id) candidates.*
    from candidates
    order by candidates.item_kind, candidates.item_id, candidates.collected_at desc
  )
  select latest.item_id, latest.item_kind, latest.protocol_number, latest.publication_date,
    latest.reference_year, latest.item_type, latest.title, latest.summary, latest.author_name,
    latest.situation, latest.source_url, latest.active, latest.collected_at,
    'camara-legislative/1.0.0'::text
  from latest
  where (item_kind_filter is null or latest.item_kind = item_kind_filter)
    and (year_filter is null or latest.reference_year = year_filter)
    and (author_filter is null or latest.author_name = nullif(btrim(author_filter), ''))
    and (query_filter is null or lower(concat_ws(' ', latest.item_id, latest.protocol_number, latest.title, latest.summary, latest.author_name)) like '%' || lower(btrim(query_filter)) || '%')
  order by latest.reference_year desc nulls last, latest.publication_date desc nulls last, latest.item_kind, latest.item_id
  limit page_size;
end;
$function$;

revoke all on function api.get_camara_legislative_items(integer, text, integer, text, text) from public;
grant execute on function api.get_camara_legislative_items(integer, text, integer, text, text) to anon, authenticated;
comment on function api.get_camara_legislative_items(integer, text, integer, text, text) is
  'Leis e indicações da Câmara com autoria somente quando declarada pela fonte oficial; sem associação aproximada.';
