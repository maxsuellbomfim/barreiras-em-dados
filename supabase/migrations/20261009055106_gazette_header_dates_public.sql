begin;

-- As funções públicas do Diário (índice, busca e edição) e a cobertura
-- diária passam a usar a data impressa no cabeçalho do PDF oficial
-- (editorial.gazette_edition_header_dates, gazette-edition-header-date/1.0.0)
-- quando a versão do documento não tem data. Em 09/10/2026 a regra derivou
-- 983 datas, coincidiu com a data do catálogo oficial em 415 de 415 edições
-- que já tinham as duas e não tem nenhuma inversão na ordem das edições;
-- 157 edições continuam sem data (cabeçalho não legível no texto extraído).
-- A data do documento, quando existe, continua prevalecendo.

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
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
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

create or replace function api.get_integral_gazette_edition(target_edition_year integer, target_edition integer)
 RETURNS TABLE(edition integer, edition_year integer, edition_date date, artifact_sha256 text, documents jsonb, methodology_version text)
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  if target_edition_year < 2000 or target_edition_year > 2100 then
    raise exception 'ano da edição fora do intervalo' using errcode = '22023';
  end if;
  if target_edition < 1 then
    raise exception 'edição deve ser positiva' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key
    from editorial.gazette_document_versions as version
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    where version.edition_year = target_edition_year
      and version.edition = target_edition
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
      version.created_at desc, version.id desc
  ), public_versions as (
    select version.*
    from editorial.gazette_document_versions as version
    where version.publication_status in ('validated', 'edition_fallback')
      and version.published_at is not null
      and version.edition_year = target_edition_year
      and version.edition = target_edition
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
      'full_text', version.public_full_text,
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
  left join editorial.gazette_edition_header_dates as header_date
    on header_date.raw_artifact_id = artifact.id
   and header_date.status = 'derived'
  group by edition_record.edition, edition_record.edition_year, artifact.sha256;
end;
$function$;

create or replace view source.querido_diario_daily_coverage
with (security_invoker = true)
as
with gazette_records as (
  select (record.payload ->> 'date')::date as published_day,
    record.source_record_key
  from raw.raw_records as record
  where record.record_type = 'querido_diario_gazette'
), documents as (
  select gazette_records.source_record_key, document.id
  from gazette_records
  join lateral (
    -- offset 0 mantém a busca por edição (o planejador estimava 22 mil
    -- linhas e voltava à varredura completa).
    select artifact.id
    from raw.raw_artifacts as artifact
    where artifact.artifact_kind = 'document'
      and artifact.metadata ->> 'source_record_key' = gazette_records.source_record_key
    offset 0
  ) as document on true
), direct_editions as (
  select distinct
    coalesce(version.edition_date, header_date.edition_date) as published_day,
    version.edition,
    version.raw_artifact_id
  from editorial.gazette_document_versions as version
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  left join editorial.gazette_edition_header_dates as header_date
    on header_date.raw_artifact_id = version.raw_artifact_id
   and header_date.status = 'derived'
  where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
    and coalesce(version.edition_date, header_date.edition_date) is not null
), runs as (
  select run.collection_window_start::date as window_start,
    run.collection_window_end::date as window_end,
    run.status
  from source.collection_runs as run
  join source.source_endpoints as endpoint on endpoint.id = run.source_endpoint_id
  join source.data_sources as data_source on data_source.id = endpoint.data_source_id
  where data_source.slug = 'querido-diario'
), bounds as (
  select
    least(
      (select min(runs.window_start) from runs),
      (select min(gazette_records_1.published_day) from gazette_records as gazette_records_1),
      (select min(direct_editions_1.published_day) from direct_editions as direct_editions_1)
    ) as first_day,
    greatest(
      (select max(runs.window_end) from runs),
      (select max(gazette_records_1.published_day) from gazette_records as gazette_records_1),
      (select max(direct_editions_1.published_day) from direct_editions as direct_editions_1)
    ) as last_day
), days as (
  select generate_series(bounds.first_day::timestamptz, bounds.last_day::timestamptz,
    '1 day'::interval)::date as day
  from bounds
  where bounds.first_day is not null and bounds.last_day is not null
)
select days.day,
  (exists (
    select 1 from runs
    where runs.status = 'succeeded'
      and runs.window_start is not null
      and runs.window_end is not null
      and days.day >= runs.window_start
      and days.day <= runs.window_end
  )) as attempted_by_recorded_window,
  (count(distinct gazette_records.source_record_key)
    + count(distinct direct_editions.edition))::bigint as preserved_editions,
  (count(distinct documents.id)
    + count(distinct direct_editions.raw_artifact_id))::bigint as preserved_documents
from days
left join gazette_records on gazette_records.published_day = days.day
left join documents on documents.source_record_key = gazette_records.source_record_key
left join direct_editions on direct_editions.published_day = days.day
group by days.day
order by days.day;

notify pgrst, 'reload schema';

commit;
