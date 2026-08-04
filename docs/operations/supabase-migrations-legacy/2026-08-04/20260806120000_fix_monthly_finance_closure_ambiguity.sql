-- Fechamento mensal determinÃ­stico e inventÃ¡rio operacional do pipeline financeiro.
-- Nenhum total Ã© produzido por IA: a funÃ§Ã£o usa somente relatÃ³rios jÃ¡ validados
-- e preserva a distinÃ§Ã£o entre receita declarada e pagamento efetivado.

-- Recompila a funcao com a politica de conflito orientada a colunas.
-- A migration original ja foi aplicada; esta copia e idempotente.

drop function if exists api.get_public_monthly_finance_closures(integer, smallint);

create function api.get_public_monthly_finance_closures(
  page_size integer default 24,
  fiscal_year_filter smallint default null
)
returns table (
  closure_id text,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  revenue_report_amount numeric,
  revenue_report_count integer,
  revenue_line_count integer,
  expense_paid_amount numeric,
  expense_committed_amount numeric,
  expense_liquidated_amount numeric,
  expense_report_count integer,
  operational_difference_amount numeric,
  closure_status text,
  coverage_note text,
  calculation_methodology text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if page_size < 1 or page_size > 120 then
    raise exception 'page_size deve estar entre 1 e 120'
      using errcode = '22023';
  end if;

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with revenue_source_reports as (
    select
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date as period_start,
      revenue.source_document_artifact_id,
      max(revenue.report_total_period_amount) as report_amount,
      count(*)::integer as line_count
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and revenue.revenue_date is not null
      and revenue.source_document_artifact_id is not null
      and (
        fiscal_year_filter is null
        or revenue.fiscal_year = fiscal_year_filter
      )
    group by
      revenue.public_body_id,
      date_trunc('month', revenue.revenue_date)::date,
      revenue.source_document_artifact_id
  ),
  revenue_months as (
    select
      source.public_body_id,
      source.period_start,
      sum(source.report_amount) as report_amount,
      count(*)::integer as report_count,
      sum(source.line_count)::integer as line_count
    from revenue_source_reports as source
    group by source.public_body_id, source.period_start
  ),
  expense_current as (
    select distinct on (
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id
    )
      report.*
    from finance.expense_reports as report
    where report.validation_status = 'validated'
      and report.published_at is not null
      and (
        fiscal_year_filter is null
        or report.fiscal_year = fiscal_year_filter
      )
    order by
      report.public_body_id,
      report.period_start,
      report.period_end,
      report.source_document_artifact_id,
      report.version desc,
      report.created_at desc,
      report.id desc
  ),
  expense_months as (
    select
      expense.public_body_id,
      date_trunc('month', expense.period_end)::date as period_start,
      max(expense.period_end)::date as period_end,
      max(expense.total_paid_period_amount) as paid_amount,
      max(expense.total_committed_period_amount) as committed_amount,
      max(expense.total_liquidated_period_amount) as liquidated_amount,
      count(*)::integer as report_count
    from expense_current as expense
    group by expense.public_body_id, date_trunc('month', expense.period_end)::date
  ),
  periods as (
    select public_body_id, period_start from revenue_months
    union
    select public_body_id, period_start from expense_months
  )
  select
    periods.public_body_id::text || ':' || periods.period_start::text,
    extract(year from periods.period_start)::smallint,
    periods.period_start,
    (
      periods.period_start + interval '1 month - 1 day'
    )::date,
    body.name,
    revenue.report_amount,
    coalesce(revenue.report_count, 0),
    coalesce(revenue.line_count, 0),
    expense.paid_amount,
    expense.committed_amount,
    expense.liquidated_amount,
    coalesce(expense.report_count, 0),
    case
      when revenue.report_count = 1 and expense.report_count = 1
        then revenue.report_amount - expense.paid_amount
      else null
    end,
    case
      when revenue.report_count is null or expense.report_count is null
        then 'needs_data'::text
      when revenue.report_count > 1 or expense.report_count > 1
        then 'needs_review'::text
      else 'operational'::text
    end,
    case
      when revenue.report_count is null
        then 'HÃ¡ pagamentos publicados, mas ainda nÃ£o hÃ¡ relatÃ³rio de receita comparÃ¡vel.'
      when expense.report_count is null
        then 'HÃ¡ receita publicada, mas ainda nÃ£o hÃ¡ relatÃ³rio de pagamentos comparÃ¡vel.'
      when revenue.report_count > 1 or expense.report_count > 1
        then 'HÃ¡ mais de um relatÃ³rio na mesma competÃªncia; o total aguarda reconciliaÃ§Ã£o para evitar dupla contagem.'
      else 'DiferenÃ§a entre a receita total declarada no relatÃ³rio e o pagamento efetivado no mÃªs. NÃ£o Ã© superÃ¡vit fiscal.'
    end,
    'monthly-finance-closure/1.0.0'::text
  from periods
  join org.public_bodies as body on body.id = periods.public_body_id
  left join revenue_months as revenue
    on revenue.public_body_id = periods.public_body_id
   and revenue.period_start = periods.period_start
  left join expense_months as expense
    on expense.public_body_id = periods.public_body_id
   and expense.period_start = periods.period_start
  order by periods.period_start desc, body.name
  limit page_size;
end;
$function$;

revoke all on function api.get_public_monthly_finance_closures(integer, smallint)
  from public;
grant execute on function api.get_public_monthly_finance_closures(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_monthly_finance_closures(integer, smallint) is
  'Fechamento mensal determinÃ­stico: relatÃ³rio de receita versus pagamento efetivado, com estado de cobertura explÃ­cito.';

drop function if exists api.get_finance_ingestion_inventory(integer, text, text);

create function api.get_finance_ingestion_inventory(
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
    'rgf'
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
          split_part(document.source_url, '/', array_length(string_to_array(document.source_url, '/'), 1)),
          '\.pdf$','', 'i'
        ), ''),
        'Documento financeiro'
      ) as document_title,
      document.source_url,
      document.retrieved_at,
      document.sha256,
      document.byte_size,
      document.metadata ->> 'source_record_key' as source_record_key,
      document.parser_version,
      latest.status as latest_job_status,
      latest.last_error_code,
      latest.last_error_detail,
      coalesce(expense_rows.count, 0) + coalesce(revenue_rows.count, 0) as published_rows,
      case
        when coalesce(expense_rows.count, 0) > 0 then 'published'::text
        when coalesce(revenue_rows.count, 0) > 0 then 'published'::text
        when latest.status in ('failed', 'dead_lettered') then 'failed'::text
        when latest.status in ('queued', 'running', 'retry_scheduled') then 'queued'::text
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
    where document.artifact_kind = 'document'
      and document.metadata ->> 'schema_name' = 'municipal-transparency-document'
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
    'finance-ingestion-inventory/1.0.0'::text
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
  'InventÃ¡rio interno de PDFs financeiros preservados, com status de extraÃ§Ã£o/publicaÃ§Ã£o e Ãºltimo erro.';


