begin;

-- Um replay idempotente pode reutilizar o registro bruto de uma resposta de
-- catálogo anterior e preservar o PDF em um artefato de catálogo posterior.
-- O vínculo público deve seguir a identidade oficial do documento dentro do
-- mesmo endpoint, e não depender exclusivamente do parent_artifact_id físico.

create or replace function api.get_public_finance_documents(
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
    'balancetes',
    'pdc-contas-anuais',
    'pdc-receita-tributaria',
    'pdc-recursos-extraordinarios',
    'pdc-resumo-execucao-da-receita',
    'pdc-resumo-execucao-da-despesa',
    'pdc-transferencia',
    'pdc-emendas-parlamentares-receitas',
    'pdc-convenios-transferencias-realizadas',
    'pdc-obras-pdc',
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
      where child.source_endpoint_id = artifact.source_endpoint_id
        and child.artifact_kind = 'document'
        and child.metadata ->> 'schema_name'
          = 'municipal-transparency-document'
        and child.metadata ->> 'source_record_key'
          = record.source_record_key
        and child.source_url = record.payload ->> 'url'
      order by child.created_at desc, child.id desc
      limit 1
    ) as document on true
    where record.record_type in (
      'municipal_transparency_balancetes',
      'municipal_transparency_pdc-contas-anuais',
      'municipal_transparency_pdc-receita-tributaria',
      'municipal_transparency_pdc-recursos-extraordinarios',
      'municipal_transparency_pdc-resumo-execucao-da-receita',
      'municipal_transparency_pdc-resumo-execucao-da-despesa',
      'municipal_transparency_pdc-transferencia',
      'municipal_transparency_pdc-emendas-parlamentares-receitas',
      'municipal_transparency_pdc-convenios-transferencias-realizadas',
      'municipal_transparency_pdc-obras-pdc',
      'municipal_transparency_rreo',
      'municipal_transparency_rgf'
    )
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
      nullif(btrim(candidate.payload ->> 'informacoes'), ''),
      nullif(btrim(candidate.payload ->> 'descricao'), ''),
      'Documento financeiro oficial'
    ),
    candidate.payload ->> 'data',
    case
      when coalesce(candidate.payload ->> 'ano', candidate.payload ->> 'ano_ref')
        ~ '^[0-9]{4}$'
      then coalesce(candidate.payload ->> 'ano', candidate.payload ->> 'ano_ref')::smallint
      else null
    end,
    case
      when coalesce(candidate.payload ->> 'mes', candidate.payload ->> 'mes_ref')
        ~ '^[0-9]{1,2}$'
      then coalesce(candidate.payload ->> 'mes', candidate.payload ->> 'mes_ref')::smallint
      else null
    end,
    nullif(btrim(candidate.payload ->> 'descricao'), ''),
    candidate.payload ->> 'url',
    candidate.api_source_url,
    candidate.artifact_sha256,
    candidate.retrieved_at,
    'api_response_preserved',
    'public-finance-documents/1.6.0',
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
  'Catálogo financeiro com vínculo idempotente por endpoint, chave oficial e URL do PDF preservado; não calcula saldo de dívida.';

notify pgrst, 'reload schema';

commit;
