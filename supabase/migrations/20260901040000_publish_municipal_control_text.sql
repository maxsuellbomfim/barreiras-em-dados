begin;

create or replace function api.search_public_municipal_control_documents(
  search_query text default null,
  page_size integer default 20,
  page_offset integer default 0
)
returns table (
  document_id uuid,
  title text,
  reference_date text,
  excerpt text,
  document_source_url text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  total_count integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 50 then
    raise exception 'page_size deve estar entre 1 e 50'
      using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 10000 then
    raise exception 'page_offset deve estar entre 0 e 10000'
      using errcode = '22023';
  end if;
  if length(coalesce(search_query, '')) > 100 then
    raise exception 'search_query deve ter no maximo 100 caracteres'
      using errcode = '22023';
  end if;

  return query
  with current_records as (
    select
      record.id,
      record.source_record_key,
      record.payload,
      record.created_at,
      artifact.source_endpoint_id,
      row_number() over (
        partition by coalesce(record.source_record_key, record.id::text)
        order by record.created_at desc, record.id desc
      ) as current_row
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    where record.record_type = 'municipal_transparency_pdc-contas-anuais'
      and record.payload ->> 'url' ~ '^https://'
  ), verified as (
    select
      record.id,
      coalesce(
        nullif(btrim(record.payload ->> 'titulo'), ''),
        nullif(btrim(record.payload ->> 'informacoes'), ''),
        'Documento da base legal municipal'
      ) as title,
      record.payload ->> 'data' as reference_date,
      page.text_content as full_text,
      document.source_url,
      document.sha256 as artifact_sha256,
      document.created_at as collected_at,
      record.created_at as record_created_at
    from current_records as record
    join lateral (
      select child.id, child.source_url, child.sha256, child.created_at
      from raw.raw_artifacts as child
      where child.source_endpoint_id = record.source_endpoint_id
        and child.artifact_kind = 'document'
        and child.metadata ->> 'schema_name' = 'municipal-transparency-document'
        and child.metadata ->> 'document_role' = 'docx'
        and child.metadata ->> 'source_record_key' = record.source_record_key
        and child.source_url = record.payload ->> 'url'
        and child.content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        and child.http_status between 200 and 299
      order by child.created_at desc, child.id desc
      limit 1
    ) as document on true
    join lateral (
      select document_page.text_content
      from raw.document_pages as document_page
      where document_page.raw_artifact_id = document.id
        and document_page.page_number = 1
        and document_page.parser_version = 'docx-wordprocessingml/1.0.0'
        and document_page.extraction_method = 'embedded_text'
        and nullif(btrim(document_page.text_content), '') is not null
        and document_page.text_sha256 ~ '^[0-9a-f]{64}$'
      order by document_page.created_at desc, document_page.id desc
      limit 1
    ) as page on true
    where record.current_row = 1
      and exists (
        select 1
        from raw.extraction_jobs as job
        where job.raw_artifact_id = document.id
          and job.job_type = 'municipal_docx_text'
          and job.status = 'succeeded'
      )
  ), filtered as (
    select verified.*
    from verified
    where nullif(btrim(search_query), '') is null
      or position(
        lower(btrim(search_query)) in lower(
          verified.title || ' ' || coalesce(verified.reference_date, '') ||
          ' ' || verified.full_text
        )
      ) > 0
  )
  select
    filtered.id,
    filtered.title,
    filtered.reference_date,
    left(filtered.full_text, 360),
    filtered.source_url,
    filtered.artifact_sha256,
    filtered.collected_at,
    count(*) over ()::integer,
    'municipal-control-text/1.0.0'
  from filtered
  order by filtered.record_created_at desc, filtered.id desc
  limit page_size
  offset page_offset;
end;
$function$;

create or replace function api.get_public_municipal_control_document(
  document_id_filter uuid
)
returns table (
  document_id uuid,
  title text,
  reference_date text,
  description text,
  full_text text,
  document_source_url text,
  document_artifact_sha256 text,
  text_sha256 text,
  parser_version text,
  collected_at timestamptz,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
  with current_record as (
    select
      record.id,
      record.source_record_key,
      record.payload,
      artifact.source_endpoint_id
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    where record.id = document_id_filter
      and record.record_type = 'municipal_transparency_pdc-contas-anuais'
      and record.payload ->> 'url' ~ '^https://'
      and not exists (
        select 1
        from raw.raw_records as newer
        where newer.record_type = record.record_type
          and coalesce(newer.source_record_key, newer.id::text)
            = coalesce(record.source_record_key, record.id::text)
          and (newer.created_at, newer.id) > (record.created_at, record.id)
      )
  )
  select
    record.id,
    coalesce(
      nullif(btrim(record.payload ->> 'titulo'), ''),
      nullif(btrim(record.payload ->> 'informacoes'), ''),
      'Documento da base legal municipal'
    ),
    record.payload ->> 'data',
    nullif(btrim(record.payload ->> 'descricao'), ''),
    page.text_content,
    document.source_url,
    document.sha256,
    page.text_sha256,
    page.parser_version,
    document.created_at,
    'municipal-control-text/1.0.0'
  from current_record as record
  join lateral (
    select child.id, child.source_url, child.sha256, child.created_at
    from raw.raw_artifacts as child
    where child.source_endpoint_id = record.source_endpoint_id
      and child.artifact_kind = 'document'
      and child.metadata ->> 'schema_name' = 'municipal-transparency-document'
      and child.metadata ->> 'document_role' = 'docx'
      and child.metadata ->> 'source_record_key' = record.source_record_key
      and child.source_url = record.payload ->> 'url'
      and child.content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      and child.http_status between 200 and 299
    order by child.created_at desc, child.id desc
    limit 1
  ) as document on true
  join lateral (
    select document_page.text_content, document_page.text_sha256,
      document_page.parser_version
    from raw.document_pages as document_page
    where document_page.raw_artifact_id = document.id
      and document_page.page_number = 1
      and document_page.parser_version = 'docx-wordprocessingml/1.0.0'
      and document_page.extraction_method = 'embedded_text'
      and nullif(btrim(document_page.text_content), '') is not null
      and document_page.text_sha256 ~ '^[0-9a-f]{64}$'
    order by document_page.created_at desc, document_page.id desc
    limit 1
  ) as page on true
  where exists (
    select 1
    from raw.extraction_jobs as job
    where job.raw_artifact_id = document.id
      and job.job_type = 'municipal_docx_text'
      and job.status = 'succeeded'
  );
$function$;

revoke all on function api.search_public_municipal_control_documents(text, integer, integer) from public;
revoke all on function api.get_public_municipal_control_document(uuid) from public;
grant execute on function api.search_public_municipal_control_documents(text, integer, integer)
  to anon, authenticated;
grant execute on function api.get_public_municipal_control_document(uuid)
  to anon, authenticated;

comment on function api.search_public_municipal_control_documents(text, integer, integer) is
  'Lista paginada e pesquisavel do texto literal verificado da base legal municipal; nao publica tabelas raw nem demonstrativos financeiros.';
comment on function api.get_public_municipal_control_document(uuid) is
  'Detalhe do texto literal de um DOCX oficial verificado, com fonte e hashes de procedencia.';

notify pgrst, 'reload schema';

commit;
