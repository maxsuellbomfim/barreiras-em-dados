-- Diário: índice de edições sem o texto integral. A lista pública só mostra
-- título, tipo e páginas de cada documento, mas as RPCs de edição devolviam o
-- texto de todos (cerca de 3,4 MB por página de 20 edições), acima do limite
-- de 2 MB do cache de dados do Next: cada visita ia ao banco (3,6–4,5 s).
-- As funções abaixo são cópias das atuais sem a chave full_text; a busca
-- continua procurando no texto público mascarado.

create function api.get_integral_gazette_index_page(
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
begin
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
  )
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', editorial.mask_cpf_v1(version.literal_title),
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order),
    'integral-gazette-documents/1.1.0'::text
  from all_batches as edition_record
  join public_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc
  limit page_size offset page_offset;
end;
$function$;
revoke all on function api.get_integral_gazette_index_page(integer, integer) from public;
grant execute on function api.get_integral_gazette_index_page(integer, integer) to anon, authenticated;

create function api.search_integral_gazette_index(
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
  edition_query text;
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
  edition_query := case
    when normalized_query ~ '^[0-9]{1,3}(\.[0-9]{3})+(/[0-9]{4})?$'
      then replace(normalized_query, '.', '')
    else normalized_query end;

  return query
  with all_batches as (
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key,
      coalesce(edition_query = version.edition::text
        or edition_query = version.edition::text || '/' || version.edition_year::text,
        false) as exact_match
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
    where normalized_query is null or edition_record.exact_match
      or position(normalized_query in lower(editorial.mask_cpf_v1(version.literal_title))) > 0
      or position(normalized_query in lower(version.public_full_text)) > 0
  )
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', editorial.mask_cpf_v1(version.literal_title),
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order),
    'integral-gazette-documents/1.1.0'::text
  from all_batches as edition_record
  join public_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
  join matching_editions
    on matching_editions.edition = edition_record.edition
   and matching_editions.edition_year = edition_record.edition_year
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year,
    edition_record.exact_match, artifact.sha256
  order by edition_record.exact_match desc,
    edition_record.edition_year desc, edition_record.edition desc
  limit page_size offset page_offset;
end;
$function$;
revoke all on function api.search_integral_gazette_index(text, integer, integer) from public;
grant execute on function api.search_integral_gazette_index(text, integer, integer) to anon, authenticated;
