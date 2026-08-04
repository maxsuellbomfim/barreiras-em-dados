-- ADR 0017: o catálogo oficial deve aparecer mesmo quando o PDF integral
-- ainda não foi preservado. Isso evita que uma edição recém-publicada fique
-- invisível enquanto o processamento pesado do documento não termina.

drop function if exists api.get_official_diary_catalog(integer);

create function api.get_official_diary_catalog(
  page_size integer default 40
)
returns table (
  catalog_id uuid,
  edition integer,
  edition_year integer,
  edition_date date,
  official_title text,
  official_summary text,
  official_publication_url text,
  catalog_url text,
  artifact_sha256 text,
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
  select *
  from (
    select distinct on ((record.payload ->> 'edition')::integer)
      record.id,
      (record.payload ->> 'edition')::integer,
      extract(year from (record.payload ->> 'date')::date)::integer,
      (record.payload ->> 'date')::date,
      nullif(btrim(record.payload ->> 'title'), ''),
      nullif(btrim(record.payload ->> 'summary'), ''),
      nullif(record.payload ->> 'publication_url', ''),
      nullif(record.payload ->> 'catalog_url', ''),
      artifact.sha256,
      record.collected_at,
      'official-diary-catalog/1.0.0'::text
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    where record.record_type = 'barreiras_diario_publication'
      and record.payload ->> 'edition' ~ '^[0-9]+$'
      and record.payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    order by
      (record.payload ->> 'edition')::integer desc,
      record.collected_at desc,
      record.id desc
  ) as latest
  order by edition desc
  limit page_size;
end;
$function$;

revoke all on function api.get_official_diary_catalog(integer) from public;
grant execute on function api.get_official_diary_catalog(integer)
  to anon, authenticated;

comment on function api.get_official_diary_catalog(integer) is
  'Metadados oficiais do catálogo do Diário, inclusive edições ainda sem PDF processado.';
