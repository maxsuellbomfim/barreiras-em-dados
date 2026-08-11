begin;

create function api.search_integral_gazette_editions(
  query_text text default null,
  page_size integer default 21,
  page_offset integer default 0
)
returns table (
  edition integer,
  edition_year integer,
  edition_date date,
  artifact_sha256 text,
  documents jsonb,
  methodology_version text
)
language plpgsql stable security definer set search_path = ''
as $function$
declare
  normalized_query text := nullif(lower(btrim(query_text)), '');
begin
  if normalized_query is not null and length(normalized_query) > 120 then
    raise exception 'query_text deve ter no máximo 120 caracteres' using errcode = '22023';
  end if;
  if page_size < 1 or page_size > 101 then
    raise exception 'page_size deve estar entre 1 e 101' using errcode = '22023';
  end if;
  if page_offset < 0 then
    raise exception 'page_offset deve ser maior ou igual a zero' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key
    from editorial.gazette_document_versions as version
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
      version.created_at desc, version.id desc
  ), public_versions as (
    select version.*
    from editorial.gazette_document_versions as version
    where version.publication_status in ('validated', 'edition_fallback')
      and version.published_at is not null
  ), matching_editions as (
    select distinct version.edition, version.edition_year
    from all_batches as edition_record
    join public_versions as version
      on version.edition = edition_record.edition
     and version.edition_year = edition_record.edition_year
     and version.batch_idempotency_key = edition_record.batch_idempotency_key
    where normalized_query is null
      or position(normalized_query in lower(version.literal_title)) > 0
      or position(normalized_query in lower(version.full_text)) > 0
  )
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', version.literal_title,
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'full_text', version.full_text,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order)
      filter (where normalized_query is null
        or position(normalized_query in lower(version.literal_title)) > 0
        or position(normalized_query in lower(version.full_text)) > 0),
    'integral-gazette-documents/1.0.0'::text
  from all_batches as edition_record
  join public_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
  join matching_editions
    on matching_editions.edition = edition_record.edition
   and matching_editions.edition_year = edition_record.edition_year
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.search_integral_gazette_editions(text, integer, integer) from public;
grant execute on function api.search_integral_gazette_editions(text, integer, integer) to anon, authenticated;
comment on function api.search_integral_gazette_editions(text, integer, integer) is
  'Busca literal, paginada e case-insensitive no texto preservado do Diário Oficial integral.';

commit;
