-- Liga cada catalogo JSON municipal ao PDF filho preservado no Storage.
-- A resposta da API continua sendo a origem; o PDF e uma evidencia derivada.

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
