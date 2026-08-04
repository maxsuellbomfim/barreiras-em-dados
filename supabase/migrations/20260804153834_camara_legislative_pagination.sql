-- Paginação pública do acervo legislativo. A consulta continua determinística
-- e devolve a contagem total do recorte para a navegação da interface.

create or replace function api.get_camara_legislative_page(
  page_size integer default 50,
  page_offset integer default 0,
  item_kind_filter text default null,
  year_filter integer default null,
  author_filter text default null,
  query_filter text default null
)
returns table (
  total_count bigint,
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
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 100000 then
    raise exception 'page_offset fora do intervalo' using errcode = '22023';
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
      case when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/') end as source_url,
      case when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end as active,
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
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_protocolo' <> '0000-00-00' then record.payload ->> 'data_protocolo'
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data_aprovacao' <> '0000-00-00' then record.payload ->> 'data_aprovacao'
        when record.payload ->> 'data' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' and record.payload ->> 'data' <> '0000-00-00' then record.payload ->> 'data' end,
      case when record.payload ->> 'data_protocolo' ~ '^[0-9]{4}' then left(record.payload ->> 'data_protocolo', 4)::integer
        when record.payload ->> 'data_aprovacao' ~ '^[0-9]{4}' then left(record.payload ->> 'data_aprovacao', 4)::integer end,
      nullif(btrim(record.payload ->> 'tipo'), ''),
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      nullif(btrim(coalesce(record.payload ->> 'autoria', record.payload ->> 'autor')), ''),
      nullif(btrim(record.payload ->> 'situacao'), ''),
      case when record.payload ->> 'url' ~ '^https://' then record.payload ->> 'url'
        when record.payload ->> 'url' ~ '^[A-Za-z0-9._/-]+$' then 'https://portaldatransparencia.cmbarreiras.ba.gov.br/' || ltrim(record.payload ->> 'url', '/') end,
      case when lower(record.payload ->> 'ativo') in ('true', '1', 'sim') then true
        when lower(record.payload ->> 'ativo') in ('false', '0', 'nao', 'não') then false end,
      record.collected_at
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_indicacoes'
      and length(btrim(record.payload ->> 'id_indicacao')) > 0
      and length(btrim(record.payload ->> 'informacoes')) > 0
  ), latest as (
    select distinct on (candidates.item_kind, candidates.item_id) candidates.*
    from candidates
    order by candidates.item_kind, candidates.item_id, candidates.collected_at desc
  ), filtered as (
    select latest.*
    from latest
    where (item_kind_filter is null or latest.item_kind = item_kind_filter)
      and (year_filter is null or latest.reference_year = year_filter)
      and (author_filter is null or latest.author_name = nullif(btrim(author_filter), ''))
      and (query_filter is null or lower(concat_ws(' ', latest.item_id, latest.protocol_number, latest.title, latest.summary, latest.author_name)) like '%' || lower(btrim(query_filter)) || '%')
  )
  select count(*) over () as total_count, filtered.item_id, filtered.item_kind,
    filtered.protocol_number, filtered.publication_date, filtered.reference_year,
    filtered.item_type, filtered.title, filtered.summary, filtered.author_name,
    filtered.situation, filtered.source_url, filtered.active, filtered.collected_at,
    'camara-legislative/1.0.0'::text
  from filtered
  order by filtered.reference_year desc nulls last, filtered.publication_date desc nulls last,
    filtered.item_kind, filtered.item_id
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.get_camara_legislative_page(integer, integer, text, integer, text, text) from public;
grant execute on function api.get_camara_legislative_page(integer, integer, text, integer, text, text) to anon, authenticated;
comment on function api.get_camara_legislative_page(integer, integer, text, integer, text, text) is
  'Página do acervo legislativo com total determinístico do recorte; autoria somente quando declarada pela fonte.';
