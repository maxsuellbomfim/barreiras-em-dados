begin;

-- A versão inicial comparava o registro solicitado com toda raw.raw_records por
-- meio de uma subconsulta correlacionada. Em produção, essa verificação excedeu
-- o statement_timeout. O ranking abaixo usa o índice por record_type e
-- source_record_key e restringe o universo aos seis registros desta série.
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
  with ranked_records as materialized (
    select
      record.id,
      record.source_record_key,
      record.payload,
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
  ), current_record as (
    select ranked.id, ranked.source_record_key, ranked.payload,
      ranked.source_endpoint_id
    from ranked_records as ranked
    where ranked.current_row = 1
      and ranked.id = document_id_filter
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

revoke all on function api.get_public_municipal_control_document(uuid) from public;
grant execute on function api.get_public_municipal_control_document(uuid)
  to anon, authenticated;

comment on function api.get_public_municipal_control_document(uuid) is
  'Detalhe literal de DOCX municipal verificado; seleciona a versão atual no universo restrito da base legal para evitar varredura correlacionada de raw_records.';

notify pgrst, 'reload schema';

commit;
