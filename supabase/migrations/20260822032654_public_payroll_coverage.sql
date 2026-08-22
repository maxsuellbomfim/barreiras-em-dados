begin;

create function api.get_public_payroll_coverage(
  month_limit integer default 120
)
returns table (
  reference_month text,
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
    raise exception 'limite de cobertura da folha invalido'
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
  ), exact_catalog_records as (
    select distinct on (record.source_record_key)
      record.id,
      record.source_record_key,
      record.payload,
      record.collected_at,
      origin_artifact.source_endpoint_id,
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
    where data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and record.record_type = 'municipal_transparency_servidores'
      and record.payload ->> 'ano_ref' ~ '^(20[2-9][0-9]|2100)$'
      and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
      and make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) >= date '2021-01-01'
      and (
        (
          record.payload ->> 'tipo' = '1'
          and regexp_replace(
            btrim(translate(
              normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
              U&'\0300\0301\0302\0303\0308\0327',
              ''
            )),
            '[[:space:]]+', ' ', 'g'
          ) in (
            'relacao de servidores',
            'relacao servidores',
            'relacao de servidores 13o salario'
          )
        )
        or (
          coalesce(trim(record.payload ->> 'tipo'), '') = ''
          and regexp_replace(
            btrim(translate(
              normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
              U&'\0300\0301\0302\0303\0308\0327',
              ''
            )),
            '[[:space:]]+', ' ', 'g'
          ) = 'relacao de servidores'
        )
      )
    order by record.source_record_key, record.collected_at desc, record.id desc
  ), catalog_months as (
    select
      record.reference_month,
      count(*)::integer as document_count,
      (array_agg(
        record.payload ->> 'url'
        order by record.collected_at desc, record.id desc
      ))[1] as document_url
    from exact_catalog_records as record
    group by record.reference_month
  ), preserved_documents as (
    select distinct on (record.source_record_key)
      record.reference_month,
      record.source_record_key,
      document.id,
      document.source_url,
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
      count(*)::integer as document_count,
      (array_agg(
        document.source_url
        order by document.retrieved_at desc, document.id desc
      ))[1] as document_url,
      (array_agg(
        document.sha256
        order by document.retrieved_at desc, document.id desc
      ))[1] as document_sha256
    from preserved_documents as document
    group by document.reference_month
  ), current_components as (
    select aggregate.*
    from hr.payroll_report_aggregates as aggregate
    join org.public_bodies as public_body
      on public_body.id = aggregate.public_body_id
    where public_body.ibge_code = '2903201'
      and public_body.body_type = 'executive'
      and aggregate.validation_state = 'validated'
      and not exists (
        select 1
        from hr.payroll_report_aggregate_invalidations as invalidation
        where invalidation.aggregate_id = aggregate.id
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregates as successor
        where successor.supersedes_id = aggregate.id
          and successor.validation_state <> 'rejected'
      )
  ), published_months as (
    select component.reference_month
    from current_components as component
    group by component.reference_month, component.public_body_id
    having count(*) filter (where component.payroll_cycle = 'regular') = 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_advance'
      ) <= 1
      and count(*) filter (
        where component.payroll_cycle = 'thirteenth_final'
      ) <= 1
  ), conflicted_months as (
    select distinct aggregate.reference_month
    from hr.payroll_report_aggregate_invalidations as invalidation
    join hr.payroll_report_aggregates as aggregate
      on aggregate.id = invalidation.aggregate_id
    join org.public_bodies as public_body
      on public_body.id = aggregate.public_body_id
    where public_body.ibge_code = '2903201'
      and public_body.body_type = 'executive'
      and invalidation.reason_code = 'mixed_payroll_cycle_header'
  ), latest_month as (
    select max(candidate.reference_month) as reference_month
    from (
      select catalog.reference_month from catalog_months as catalog
      union all
      select published.reference_month from published_months as published
      union all
      select conflict.reference_month from conflicted_months as conflict
    ) as candidate
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
    case
      when published.reference_month is not null then 'published'
      when conflict.reference_month is not null then 'source_conflict'
      when catalog.reference_month is not null then 'processing_pending'
      else 'document_not_found'
    end,
    case
      when published.reference_month is not null then
        'Totais validados por código e publicados com o PDF oficial.'
      when conflict.reference_month is not null then
        'O documento oficial mistura ciclos da folha que não podem ser separados com segurança. Os valores ficam fora do total.'
      when catalog.reference_month is not null then
        'A fonte lista a folha oficial, mas o documento ainda não concluiu todas as validações determinísticas. Nenhum valor foi presumido.'
      else
        'A consulta completa ao catálogo oficial não localizou uma Relação de Servidores para esta competência. Isso não significa gasto zero.'
    end,
    coalesce(catalog.document_count, 0),
    coalesce(preserved.document_count, 0),
    case
      when catalog.reference_month is null then evidence.catalog_url
      else coalesce(preserved.document_url, catalog.document_url)
    end,
    preserved.document_sha256,
    evidence.completed_at,
    'payroll-coverage/1.0.0'::text
  from months as month
  cross join catalog_evidence as evidence
  left join catalog_months as catalog
    on catalog.reference_month = month.reference_month
  left join preserved_months as preserved
    on preserved.reference_month = month.reference_month
  left join published_months as published
    on published.reference_month = month.reference_month
  left join conflicted_months as conflict
    on conflict.reference_month = month.reference_month
  order by month.reference_month desc;
end;
$function$;

revoke all on function api.get_public_payroll_coverage(integer) from public;
grant execute on function api.get_public_payroll_coverage(integer)
  to anon, authenticated;

comment on function api.get_public_payroll_coverage(integer) is
  'Explica a situação de cada competência da folha desde 2021 a partir de catálogo oficial completo, PDFs preservados, invalidações append-only e totais públicos; ausência nunca representa gasto zero.';

notify pgrst, 'reload schema';

commit;
