-- Corrige as projeções públicas financeiras que ficaram fora da primeira
-- aplicação de migrations em produção.
-- A versão abaixo é a versão do contrato público, não a versão interna do
-- parser que gravou cada linha financeira.

drop function if exists api.get_public_finance_documents(integer, text);

create function api.get_public_finance_documents(
  page_size integer default 100,
  resource_filter text default null
)
returns table (
  document_id uuid,
  source_resource text,
  title text,
  reference_date text,
  fiscal_year smallint,
  reference_month smallint,
  description text,
  document_url text,
  api_source_url text,
  artifact_sha256 text,
  collected_at timestamptz,
  source_status text,
  methodology_version text,
  document_artifact_sha256 text,
  document_preserved boolean
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

  return query
  with candidates as (
    select
      record.id,
      split_part(record.record_type, 'municipal_transparency_', 2) as resource,
      record.payload,
      record.created_at,
      artifact.source_url as api_source_url,
      artifact.sha256 as artifact_sha256,
      artifact.retrieved_at,
      document.sha256 as document_artifact_sha256,
      document.id is not null as document_preserved,
      row_number() over (
        partition by record.record_type, coalesce(
          record.source_record_key,
          record.id::text
        )
        order by record.created_at desc, record.id desc
      ) as current_row
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    left join lateral (
      select child.id, child.sha256
      from raw.raw_artifacts as child
      where child.parent_artifact_id = artifact.id
        and child.artifact_kind = 'document'
        and child.metadata ->> 'schema_name'
          = 'municipal-transparency-document'
      order by child.created_at desc, child.id desc
      limit 1
    ) as document on true
    where record.record_type like 'municipal_transparency_pdc-%'
      and record.payload ->> 'url' ~ '^https://'
      and (
        resource_filter is null
        or split_part(record.record_type, 'municipal_transparency_', 2)
          = resource_filter
      )
  )
  select
    candidate.id,
    candidate.resource,
    coalesce(
      nullif(btrim(candidate.payload ->> 'titulo'), ''),
      nullif(btrim(candidate.payload ->> 'descricao'), ''),
      'Documento financeiro oficial'
    ),
    candidate.payload ->> 'data',
    case
      when candidate.payload ->> 'ano' ~ '^[0-9]{4}$'
      then (candidate.payload ->> 'ano')::smallint
      else null
    end,
    case
      when candidate.payload ->> 'mes' ~ '^[0-9]{1,2}$'
      then (candidate.payload ->> 'mes')::smallint
      else null
    end,
    nullif(btrim(candidate.payload ->> 'descricao'), ''),
    candidate.payload ->> 'url',
    candidate.api_source_url,
    candidate.artifact_sha256,
    candidate.retrieved_at,
    'api_response_preserved',
    'public-finance-documents/1.1.0',
    candidate.document_artifact_sha256,
    candidate.document_preserved
  from candidates as candidate
  where candidate.current_row = 1
  order by candidate.created_at desc, candidate.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_finance_documents(integer, text) from public;
grant execute on function api.get_public_finance_documents(integer, text)
  to anon, authenticated;

comment on function api.get_public_finance_documents(integer, text) is
  'Catalogo financeiro com resposta API e, quando disponivel, hash do PDF filho preservado.';

create or replace function api.get_public_revenues(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  revenue_id uuid,
  external_id text,
  fiscal_year smallint,
  revenue_date date,
  revenue_code text,
  description text,
  collected_amount numeric,
  accumulated_amount numeric,
  report_total_period_amount numeric,
  collection_direction text,
  currency text,
  public_body_name text,
  source_url text,
  document_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text,
  validation_status text
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

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with ranked as (
    select
      revenue.*,
      row_number() over (
        partition by revenue.public_body_id,
          coalesce(revenue.external_id, revenue.id::text)
        order by revenue.version desc, revenue.created_at desc, revenue.id desc
      ) as current_row
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and (
        fiscal_year_filter is null
        or revenue.fiscal_year = fiscal_year_filter
      )
  )
  select
    revenue.id,
    revenue.external_id,
    revenue.fiscal_year,
    revenue.revenue_date,
    revenue.revenue_code,
    revenue.description,
    case
      when revenue.collection_direction = 'deduction'
      then -revenue.collected_amount
      else revenue.collected_amount
    end,
    case
      when revenue.collection_direction = 'deduction'
      then -revenue.accumulated_amount
      else revenue.accumulated_amount
    end,
    revenue.report_total_period_amount,
    revenue.collection_direction,
    revenue.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    'public-revenues/1.1.0',
    revenue.validation_status
  from ranked as revenue
  join org.public_bodies as body
    on body.id = revenue.public_body_id
  join raw.raw_records as origin
    on origin.id = revenue.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = revenue.source_document_artifact_id
   and document.artifact_kind = 'document'
  where revenue.current_row = 1
  order by revenue.revenue_date desc nulls last, revenue.created_at desc,
    revenue.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_revenues(integer, smallint) from public;
grant execute on function api.get_public_revenues(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_revenues(integer, smallint) is
  'Receitas validadas com contrato publico 1.1, direcao contabil, PDF preservado e proveniencia completa.';
