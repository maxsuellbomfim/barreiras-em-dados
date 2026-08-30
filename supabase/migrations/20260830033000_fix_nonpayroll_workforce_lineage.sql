begin;

create or replace function api.get_public_nonpayroll_workforce_coverage(
  month_limit integer default 120
)
returns table (
  reference_month text,
  workforce_category text,
  category_label text,
  coverage_status text,
  coverage_note text,
  catalog_document_count integer,
  preserved_document_count integer,
  source_url text,
  artifact_sha256 text,
  catalog_checked_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if month_limit is null or month_limit < 1 or month_limit > 120 then
    raise exception 'limite de cobertura de vínculos separados inválido'
      using errcode = '22023';
  end if;

  return query
  with latest_complete_catalog as (
    select
      partition.collection_run_id,
      partition.completed_at,
      endpoint.id as endpoint_id
    from source.collection_partitions as partition
    join source.source_endpoints as endpoint
      on endpoint.id = partition.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and partition.partition_key like 'snapshot:servidores:%'
      and partition.status = 'complete'
      and partition.observed_records > 0
      and partition.collection_run_id is not null
      and partition.completed_at is not null
    order by partition.completed_at desc, partition.id desc
    limit 1
  ), catalog_evidence as (
    select
      catalog.collection_run_id,
      catalog.completed_at,
      coalesce(artifact.source_url, endpoint.base_url) as catalog_url
    from latest_complete_catalog as catalog
    join source.source_endpoints as endpoint on endpoint.id = catalog.endpoint_id
    left join lateral (
      select candidate.source_url
      from raw.raw_artifacts as candidate
      where candidate.collection_run_id = catalog.collection_run_id
        and candidate.source_endpoint_id = catalog.endpoint_id
        and candidate.artifact_kind = 'http_response'
        and candidate.source_url like 'https://%'
      order by candidate.retrieved_at desc, candidate.id desc
      limit 1
    ) as artifact on true
  ), categories as (
    select *
    from (values
      ('interns'::text, 'Estagiários'::text),
      ('outsourced_workers'::text, 'Terceirizados'::text)
    ) as category(category_code, category_label)
  ), exact_catalog_records as (
    select distinct on (record.source_record_key)
      record.id,
      record.source_record_key,
      record.payload,
      record.collected_at,
      origin_artifact.source_endpoint_id,
      category.category_code,
      category.category_label,
      make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) as reference_month
    from raw.raw_records as record
    join raw.raw_artifacts as origin_artifact
      on origin_artifact.id = record.raw_artifact_id
    join source.source_endpoints as endpoint
      on endpoint.id = origin_artifact.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    cross join lateral (
      select regexp_replace(
        btrim(translate(
          normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
          U&'\0300\0301\0302\0303\0308\0327',
          ''
        )),
        '[[:space:]]+', ' ', 'g'
      ) as value
    ) as normalized_title
    join categories as category
      on category.category_code = case
        when normalized_title.value = 'relacao de estagiarios'
          or normalized_title.value like 'relacao de estagiarios %'
          then 'interns'
        when normalized_title.value = 'relacao de terceirizados'
          or normalized_title.value like 'relacao de terceirizados %'
          then 'outsourced_workers'
        when record.payload ->> 'tipo' = '3' then 'interns'
        when record.payload ->> 'tipo' = '4' then 'outsourced_workers'
        else null
      end
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and record.record_type = 'municipal_transparency_servidores'
      and (
        record.payload ->> 'tipo' in ('3', '4')
        or normalized_title.value = 'relacao de estagiarios'
        or normalized_title.value like 'relacao de estagiarios %'
        or normalized_title.value = 'relacao de terceirizados'
        or normalized_title.value like 'relacao de terceirizados %'
      )
      and record.payload ->> 'ano_ref' ~ '^(20[2-9][0-9]|2100)$'
      and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
      and make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) >= date '2021-01-01'
    order by record.source_record_key, record.collected_at desc, record.id desc
  ), catalog_months as (
    select
      record.reference_month,
      record.category_code,
      count(*)::integer as document_count
    from exact_catalog_records as record
    group by record.reference_month, record.category_code
  ), preserved_documents as (
    select distinct on (record.source_record_key)
      record.reference_month,
      record.category_code,
      record.source_record_key,
      document.id,
      document.sha256,
      document.retrieved_at
    from exact_catalog_records as record
    join raw.raw_artifacts as document
      on document.artifact_kind = 'document'
      and document.source_endpoint_id = record.source_endpoint_id
      and document.metadata ->> 'schema_name'
        = 'municipal-transparency-document'
      and document.metadata ->> 'source_record_key'
        = record.source_record_key
      and document.source_url = record.payload ->> 'url'
    order by
      record.source_record_key,
      document.retrieved_at desc,
      document.id desc
  ), preserved_months as (
    select
      document.reference_month,
      document.category_code,
      count(*)::integer as document_count,
      (array_agg(
        document.sha256
        order by document.retrieved_at desc, document.id desc
      ))[1] as document_sha256
    from preserved_documents as document
    group by document.reference_month, document.category_code
  ), latest_month as (
    select max(record.reference_month) as reference_month
    from exact_catalog_records as record
  ), months as (
    select generated.reference_month::date
    from latest_month
    cross join lateral generate_series(
      date '2021-01-01',
      latest_month.reference_month,
      interval '1 month'
    ) as generated(reference_month)
    where latest_month.reference_month is not null
    order by generated.reference_month desc
    limit month_limit
  )
  select
    to_char(month.reference_month, 'YYYY-MM-DD'),
    category.category_code,
    category.category_label,
    case
      when preserved.document_count > 0 then 'document_preserved'
      when catalog.document_count > 0 then 'catalogued'
      else 'not_listed'
    end,
    case
      when preserved.document_count > 0 then
        'O PDF oficial foi preservado, mas o relatório contém dados pessoais e nenhum total agregado será publicado antes de uma reconciliação determinística.'
      when catalog.document_count > 0 then
        'O catálogo oficial lista o documento, mas o PDF ainda não foi preservado. Nenhum valor foi presumido.'
      else
        'O catálogo oficial completo não listou documento desta categoria no mês; isso não significa gasto zero.'
    end,
    coalesce(catalog.document_count, 0),
    coalesce(preserved.document_count, 0),
    evidence.catalog_url,
    preserved.document_sha256,
    evidence.completed_at,
    'nonpayroll-workforce-coverage/1.0.1'::text
  from months as month
  cross join categories as category
  cross join catalog_evidence as evidence
  left join catalog_months as catalog
    on catalog.reference_month = month.reference_month
   and catalog.category_code = category.category_code
  left join preserved_months as preserved
    on preserved.reference_month = month.reference_month
   and preserved.category_code = category.category_code
  order by month.reference_month desc, category.category_code;
end;
$function$;

revoke all on function api.get_public_nonpayroll_workforce_coverage(integer)
  from public;
grant execute on function api.get_public_nonpayroll_workforce_coverage(integer)
  to anon, authenticated;

comment on function api.get_public_nonpayroll_workforce_coverage(integer) is
  'Cobertura mensal separada de estagiários e terceirizados, sem nomes, CPF, dados bancários ou valores não reconciliados. Ausência no catálogo nunca representa gasto zero.';

notify pgrst, 'reload schema';

commit;
