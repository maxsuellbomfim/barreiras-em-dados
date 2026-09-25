-- Diário: CPF mascarado em todas as saídas públicas (auditoria de 25/09/2026).
-- A versão literal continua intacta e verificada contra os blocos do PDF; o
-- texto público é derivado dela por regra determinística e versionada.
-- Regra 1: formato 000.000.000-00 em qualquer lugar.
-- Regra 2: após o rótulo CPF/C PF/C.P.F./CIN (até 20 caracteres não numéricos),
-- 9 a 11 dígitos com separadores soltos (OCR), exceto valor com centavos;
-- CNPJ não casa porque tem 8 dígitos antes da barra.
-- Máscaras parciais publicadas pela fonte ("***.456.789-**") são mantidas.

set lock_timeout = '10s';

create function editorial.mask_cpf_v1(value text)
returns text
language sql
immutable
strict
parallel safe
set search_path = ''
as $function$
  select pg_catalog.regexp_replace(
    pg_catalog.regexp_replace(
      value,
      '(\m(?:C\.?[[:space:]]?P\.?[[:space:]]?F|CIN)\M[^0-9]{0,20})(?![0-9.]*,[0-9]{2}([^0-9]|$))[0-9](?:[.,[:space:]-]{0,2}[0-9]){8,10}(?![0-9])',
      '\1***.***.***-**',
      'gi'
    ),
    '(?<![0-9])[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}(?![0-9])',
    '***.***.***-**',
    'g'
  )
$function$;

comment on function editorial.mask_cpf_v1(text) is
  'cpf-mask/1.0.0: máscara determinística de CPF para projeções públicas.';

alter table editorial.gazette_document_versions
  add column public_full_text text
  generated always as (editorial.mask_cpf_v1(full_text)) stored;

comment on column editorial.gazette_document_versions.public_full_text is
  'Texto público: full_text com CPF mascarado por editorial.mask_cpf_v1 (cpf-mask/1.0.0). text_sha256 continua sendo o hash do texto literal.';

create or replace function api.get_integral_gazette_edition(
  target_edition_year integer,
  target_edition integer
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
    max(version.edition_date), artifact.sha256,
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
  group by edition_record.edition, edition_record.edition_year, artifact.sha256;
end;
$function$;

create or replace function api.get_integral_gazette_editions(page_size integer default 20)
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
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    -- A fonte direta vence replays do Querido Diário da mesma edição; dentro
    -- da mesma proveniência, a versão mais recente é a vigente.
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
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc
  limit page_size;
end;
$function$;

create or replace function api.get_integral_gazette_editions_page(
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
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc
  limit page_size offset page_offset;
end;
$function$;

create or replace function api.search_integral_gazette_editions(
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

create or replace function api.get_approved_gazette_acts(
  page_size integer default 50
)
returns table (
  act_id uuid,
  act_type text,
  person_name text,
  position_title text,
  position_symbol text,
  organization text,
  gazette_date date,
  gazette_url text,
  excerpt text,
  assisted_summary text,
  assisted_provider text,
  approved_at timestamptz,
  artifact_sha256 text,
  extractor_version text,
  review_mode text,
  text_source text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  with latest_reviews as materialized (
    select distinct on (review.target_id)
      review.target_id,
      review.decision,
      review.reviewed_at,
      review.reviewer_subject,
      review.checklist
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
    order by review.target_id, review.created_at desc, review.id desc
  ),
  approved_results as materialized (
    select
      result.*,
      review.reviewed_at,
      review.reviewer_subject,
      review.checklist as review_checklist
    from raw.extraction_results as result
    join latest_reviews as review on review.target_id = result.id
    where review.decision = 'approved'
      and result.candidate_type in ('nomeacao', 'exoneracao')
  ),
  reviewed_assists as materialized (
    select distinct on (result.id)
      result.id as act_id,
      enrichment.result_payload ->> 'summary' as summary,
      enrichment.result_payload ->> 'provider' as provider
    from approved_results as result
    join raw.extraction_results as enrichment
      on enrichment.supersedes_id = result.id
     and enrichment.candidate_type = 'assisted_enrichment'
     and enrichment.created_at <= result.reviewed_at
     and enrichment.result_payload ->> 'summary' is not null
    order by result.id, enrichment.created_at desc, enrichment.id desc
  ),
  latest_gazettes as materialized (
    select distinct on (record.source_record_key)
      record.source_record_key,
      (record.payload ->> 'date')::date as published_date,
      record.payload ->> 'url' as source_url
    from raw.raw_records as record
    where record.record_type = 'querido_diario_gazette'
      and record.source_record_key is not null
    order by record.source_record_key, record.collected_at desc
  ),
  deduped as (
    select distinct on (
      result.candidate_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}',
        ''
      )
    )
      result.id as act_id,
      result.candidate_type as act_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}'
      ) as person_name,
      coalesce(
        result.review_checklist #>> '{verification,fields,position,value}',
        result.result_payload #>> '{fields,position,value}'
      ) as position_title,
      coalesce(
        result.review_checklist #>> '{verification,fields,position_symbol,value}',
        result.result_payload #>> '{fields,position_symbol,value}'
      ) as position_symbol,
      coalesce(
        result.review_checklist #>> '{verification,fields,organization,value}',
        result.result_payload #>> '{fields,organization,value}'
      ) as organization,
      coalesce(
        gazette.published_date,
        case
          when coalesce(
            result.review_checklist #>> '{verification,fields,act_date,value}',
            result.result_payload #>> '{fields,act_date,value}'
          ) ~ '^\d{4}-\d{2}-\d{2}$'
          then coalesce(
            result.review_checklist #>> '{verification,fields,act_date,value}',
            result.result_payload #>> '{fields,act_date,value}'
          )::date
        end
      ) as gazette_date,
      coalesce(
        gazette.source_url,
        case
          when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
          then artifact.source_url
        end
      ) as gazette_url,
      editorial.mask_cpf_v1(result.result_payload ->> 'excerpt') as excerpt,
      editorial.mask_cpf_v1(assist.summary) as assisted_summary,
      assist.provider as assisted_provider,
      result.reviewed_at as approved_at,
      artifact.sha256 as artifact_sha256,
      result.extractor_version,
      case
        when result.reviewer_subject like 'automated:%' then 'automated'
        else 'human'
      end as review_mode,
      case
        when exists (
          select 1
          from raw.document_pages as ocr_page
          where ocr_page.raw_artifact_id = artifact.id
            and ocr_page.extraction_method = 'ocr'
        ) then 'ocr_transcription'
        else 'embedded_text'
      end as text_source
    from approved_results as result
    join raw.extraction_jobs as job on job.id = result.extraction_job_id
    join raw.raw_artifacts as artifact on artifact.id = job.raw_artifact_id
    left join reviewed_assists as assist on assist.act_id = result.id
    left join latest_gazettes as gazette
      on gazette.source_record_key = artifact.metadata ->> 'source_record_key'
    order by
      result.candidate_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}',
        ''
      ),
      result.reviewed_at desc
  )
  select
    deduped.act_id,
    deduped.act_type,
    deduped.person_name,
    deduped.position_title,
    deduped.position_symbol,
    deduped.organization,
    deduped.gazette_date,
    deduped.gazette_url,
    deduped.excerpt,
    deduped.assisted_summary,
    deduped.assisted_provider,
    deduped.approved_at,
    deduped.artifact_sha256,
    deduped.extractor_version,
    deduped.review_mode,
    deduped.text_source,
    'approved-gazette-acts/1.8.0'::text
  from deduped
  order by deduped.approved_at desc, deduped.act_id
  limit page_size;
end;
$function$;

create or replace function api.get_edition_digests(
  page_size integer default 20
)
returns table (
  digest_id uuid,
  edition integer,
  edition_year integer,
  edition_date date,
  items jsonb,
  stats jsonb,
  gazette_url text,
  artifact_sha256 text,
  published_at timestamptz,
  review_mode text,
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
    select distinct on ((result.result_payload ->> 'edition')::int)
      result.id,
      (result.result_payload ->> 'edition')::int as digest_edition,
      (result.result_payload ->> 'year')::int as digest_year,
      coalesce(
        case
          when result.result_payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          then (result.result_payload ->> 'date')::date
        end,
        (
          select min((record.payload ->> 'date')::date)
          from raw.raw_records as record
          where record.record_type = 'querido_diario_gazette'
            and record.source_record_key = artifact.metadata ->> 'source_record_key'
            and record.payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        )
      ) as digest_date,
      editorial.mask_cpf_v1((result.result_payload -> 'items')::text)::jsonb,
      result.result_payload -> 'stats',
      artifact.source_url,
      artifact.sha256,
      latest.reviewed_at,
      case
        when latest.reviewer_subject like 'automated:%' then 'automated'
        else 'human'
      end,
      'edition-digests/1.3.0'::text
    from raw.extraction_results as result
    join raw.extraction_jobs as job
      on job.id = result.extraction_job_id
    join raw.raw_artifacts as artifact
      on artifact.id = job.raw_artifact_id
    join lateral (
      select review.decision, review.reviewed_at, review.reviewer_subject
      from editorial.editorial_reviews as review
      where review.target_type = 'raw.extraction_results'
        and review.target_id = result.id
      order by review.created_at desc, review.id desc
      limit 1
    ) as latest on true
    where result.candidate_type = 'edition_digest'
      and latest.decision = 'approved'
    order by
      (result.result_payload ->> 'edition')::int desc,
      latest.reviewed_at desc
  ) as deduped
  limit page_size;
end;
$function$;
