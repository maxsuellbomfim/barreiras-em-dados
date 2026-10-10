begin;

-- Depois do backfill 2021-2022 (14,6 mil versões de documento), a escolha do
-- lote de cada edição no índice e na busca do Diário lia as linhas largas das
-- versões (com o texto integral) e os metadados de 1,5 mil artefatos: 3 s no
-- índice e cancelamentos pelo limite de 3 s do papel anônimo ao longo de
-- 09/10/2026. Mesma regra de escolha (PDF direto antes do Querido Diário, a
-- versão mais nova primeiro), agora respondida só por índices enxutos.
-- 3,0 s -> 0,26 s.
create index if not exists gazette_document_versions_edition_batch_idx
  on editorial.gazette_document_versions (edition_year, edition, created_at desc, id desc)
  include (batch_idempotency_key, raw_artifact_id);

create index if not exists raw_artifacts_gazette_direct_id_idx
  on raw.raw_artifacts (id)
  where (metadata ->> 'schema_name') = 'gazette-direct-edition';

create or replace function api.get_integral_gazette_index_page(
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
language plpgsql
stable
security definer
set search_path = ''
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
    order by version.edition_year, version.edition,
      case when exists (
        select 1 from raw.raw_artifacts as artifact
        where artifact.id = version.raw_artifact_id
          and artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
      ) then 0 else 1 end,
      version.created_at desc, version.id desc
  ), page_editions as materialized (
    select edition_record.*
    from all_batches as edition_record
    where exists (
      select 1 from editorial.gazette_document_versions as version
      where version.edition = edition_record.edition
        and version.edition_year = edition_record.edition_year
        and version.batch_idempotency_key = edition_record.batch_idempotency_key
        and version.publication_status in ('validated', 'edition_fallback')
        and version.published_at is not null
    )
    order by edition_record.edition_year desc, edition_record.edition desc
    limit page_size offset page_offset
  )
  -- Sem CTE com version.*: ele era materializado com o texto integral de
  -- todos os documentos (ordenação em disco depois do backfill 2021-2022).
  select edition_record.edition, edition_record.edition_year,
    coalesce(max(version.edition_date), max(header_date.edition_date)), artifact.sha256,
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
  from page_editions as edition_record
  join editorial.gazette_document_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
   and version.publication_status in ('validated', 'edition_fallback')
   and version.published_at is not null
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  left join editorial.gazette_edition_header_dates as header_date
    on header_date.raw_artifact_id = artifact.id
   and header_date.status = 'derived'
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc;
end;
$function$;

create or replace function api.search_integral_gazette_index(query_text text DEFAULT NULL::text, page_size integer DEFAULT 21, page_offset integer DEFAULT 0)
 RETURNS TABLE(edition integer, edition_year integer, edition_date date, artifact_sha256 text, documents jsonb, methodology_version text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
    order by version.edition_year, version.edition,
      case when exists (
        select 1 from raw.raw_artifacts as artifact
        where artifact.id = version.raw_artifact_id
          and artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
      ) then 0 else 1 end,
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
    coalesce(max(version.edition_date), max(header_date.edition_date)), artifact.sha256,
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
  left join editorial.gazette_edition_header_dates as header_date
    on header_date.raw_artifact_id = artifact.id
   and header_date.status = 'derived'
  group by edition_record.edition, edition_record.edition_year,
    edition_record.exact_match, artifact.sha256
  order by edition_record.exact_match desc,
    edition_record.edition_year desc, edition_record.edition desc
  limit page_size offset page_offset;
end;
$function$;

notify pgrst, 'reload schema';

commit;
