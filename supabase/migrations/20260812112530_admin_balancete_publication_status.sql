-- Ensina o inventario administrativo a reconhecer balancetes que ja geraram
-- uma obrigacao publica validada. O RPC anterior contava apenas receitas e
-- linhas de despesa, classificando incorretamente esses PDFs como preservados.

create or replace function api.get_finance_ingestion_inventory(
  page_size integer default 200,
  status_filter text default null,
  resource_filter text default null
)
returns table (
  document_id uuid,
  resource text,
  document_title text,
  document_url text,
  retrieved_at timestamptz,
  artifact_sha256 text,
  byte_size bigint,
  source_record_key text,
  extraction_status text,
  latest_job_status text,
  latest_error_code text,
  latest_error_detail text,
  published_rows bigint,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 500 then
    raise exception 'page_size deve estar entre 1 e 500'
      using errcode = '22023';
  end if;
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;
  if resource_filter is not null and resource_filter not in (
    'pdc-receita-tributaria',
    'pdc-recursos-extraordinarios',
    'pdc-resumo-execucao-da-receita',
    'pdc-resumo-execucao-da-despesa',
    'pdc-transferencia',
    'pdc-emendas-parlamentares-receitas',
    'rreo',
    'rgf',
    'balancetes'
  ) then
    raise exception 'resource_filter nao permitido'
      using errcode = '22023';
  end if;
  if status_filter is not null and status_filter not in (
    'published', 'failed', 'queued', 'preserved_only'
  ) then
    raise exception 'status_filter nao permitido'
      using errcode = '22023';
  end if;

  return query
  with documents as (
    select
      document.id,
      split_part(document.metadata ->> 'source_record_key', ':', 3) as resource,
      coalesce(
        nullif(regexp_replace(
          split_part(
            document.source_url,
            '/',
            array_length(string_to_array(document.source_url, '/'), 1)
          ),
          '\.pdf$',
          '',
          'i'
        ), ''),
        'Documento financeiro'
      ) as document_title,
      document.source_url,
      document.retrieved_at,
      document.sha256,
      document.byte_size,
      document.metadata ->> 'source_record_key' as source_record_key,
      latest.status as latest_job_status,
      latest.last_error_code,
      latest.last_error_detail,
      coalesce(expense_rows.count, 0)
        + coalesce(revenue_rows.count, 0)
        + coalesce(obligation_rows.count, 0) as published_rows,
      case
        when coalesce(expense_rows.count, 0) > 0 then 'published'::text
        when coalesce(revenue_rows.count, 0) > 0 then 'published'::text
        when coalesce(obligation_rows.count, 0) > 0 then 'published'::text
        when latest.status in ('failed', 'dead_lettered') then 'failed'::text
        when latest.status in ('queued', 'running', 'retry_scheduled')
          then 'queued'::text
        else 'preserved_only'::text
      end as extraction_status
    from raw.raw_artifacts as document
    left join lateral (
      select job.status, job.last_error_code, job.last_error_detail
      from raw.extraction_jobs as job
      where job.raw_artifact_id = document.id
      order by job.updated_at desc, job.id desc
      limit 1
    ) as latest on true
    left join lateral (
      select count(*)::bigint as count
      from finance.expense_lines as line
      join finance.expense_reports as report on report.id = line.report_id
      where report.source_document_artifact_id = document.id
        and report.validation_status = 'validated'
        and report.published_at is not null
    ) as expense_rows on true
    left join lateral (
      select count(*)::bigint as count
      from finance.revenues as revenue
      where revenue.source_document_artifact_id = document.id
        and revenue.validation_status = 'validated'
        and revenue.published_at is not null
    ) as revenue_rows on true
    left join lateral (
      select count(*)::bigint as count
      from finance.public_obligations as obligation
      where obligation.source_document_artifact_id = document.id
        and obligation.validation_state in ('validated', 'reconciled')
    ) as obligation_rows on true
    where document.artifact_kind = 'document'
      and document.metadata ->> 'schema_name'
        = 'municipal-transparency-document'
      and document.source_url like 'https://barreiras.mtransparente.com.br/%'
      and (
        resource_filter is null
        or split_part(document.metadata ->> 'source_record_key', ':', 3)
          = resource_filter
      )
  )
  select
    documents.id,
    documents.resource,
    documents.document_title,
    documents.source_url,
    documents.retrieved_at,
    documents.sha256,
    documents.byte_size,
    documents.source_record_key,
    documents.extraction_status,
    documents.latest_job_status,
    documents.last_error_code,
    documents.last_error_detail,
    documents.published_rows,
    'finance-ingestion-inventory/1.1.0'::text
  from documents
  where status_filter is null or documents.extraction_status = status_filter
  order by documents.retrieved_at desc, documents.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_finance_ingestion_inventory(integer, text, text)
  from public, anon;
grant execute on function api.get_finance_ingestion_inventory(integer, text, text)
  to authenticated;

comment on function api.get_finance_ingestion_inventory(integer, text, text) is
  'Inventario interno de PDFs financeiros; conta receitas, despesas e obrigacoes publicas validadas.';
