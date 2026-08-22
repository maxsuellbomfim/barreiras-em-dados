begin;

create function hr.get_pending_payroll_documents(
  requested_limit integer,
  fiscal_year_from integer,
  fiscal_year_to integer,
  target_reference_month date default null
)
returns table (
  id text,
  sha256 text,
  object_key text,
  byte_size bigint,
  parent_record_id text,
  source_url text,
  reference_month date
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if requested_limit is null or requested_limit < 1 or requested_limit > 20 then
    raise exception 'limite de documentos da folha invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_from is null or fiscal_year_to is null
    or fiscal_year_from < 2021 or fiscal_year_to > 2100
    or fiscal_year_from > fiscal_year_to then
    raise exception 'intervalo fiscal da folha invalido'
      using errcode = '22023';
  end if;
  if target_reference_month is not null and (
    target_reference_month <> date_trunc('month', target_reference_month)::date
    or extract(year from target_reference_month)::integer
      not between fiscal_year_from and fiscal_year_to
  ) then
    raise exception 'competencia da folha invalida'
      using errcode = '22023';
  end if;

  return query
  with candidates as (
    select distinct on (document.id)
      document.id::text as id,
      document.sha256,
      document.object_key,
      document.byte_size,
      record.id::text as parent_record_id,
      document.source_url,
      make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) as reference_month,
      document.created_at
    from raw.raw_artifacts as document
    join raw.raw_artifacts as parent_artifact
      on parent_artifact.id = document.parent_artifact_id
    join raw.raw_records as record
      on record.raw_artifact_id = parent_artifact.id
    join source.source_endpoints as endpoint
      on endpoint.id = parent_artifact.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    where document.artifact_kind = 'document'
      and data_source.slug = 'prefeitura-barreiras-transparencia'
      and endpoint.slug = 'dados-abertos-api'
      and document.metadata ->> 'schema_name'
        = 'municipal-transparency-document'
      and document.metadata ->> 'source_record_key'
        = record.source_record_key
      and document.source_url = record.payload ->> 'url'
      and record.record_type = 'municipal_transparency_servidores'
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
      and (
        record.payload ->> 'tipo' = '1'
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
      and record.payload ->> 'ano_ref' ~ '^(20[2-9][0-9]|2100)$'
      and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
      and (record.payload ->> 'ano_ref')::integer
        between fiscal_year_from and fiscal_year_to
      and make_date(
        (record.payload ->> 'ano_ref')::integer,
        (record.payload ->> 'mes_ref')::integer,
        1
      ) = coalesce(
        target_reference_month,
        make_date(
          (record.payload ->> 'ano_ref')::integer,
          (record.payload ->> 'mes_ref')::integer,
          1
        )
      )
      and not exists (
        select 1
        from hr.payroll_report_aggregates as aggregate
        where aggregate.source_document_artifact_id = document.id
          and aggregate.parser_version = 'payroll-report-aggregate/1.3.0'
      )
      and not exists (
        select 1
        from raw.extraction_jobs as job
        where job.raw_artifact_id = document.id
          and job.job_type = 'payroll_report_publication/1.2.0'
          and job.status in ('failed', 'dead_lettered')
      )
    order by document.id, record.created_at desc, record.id desc
  )
  select
    candidate.id,
    candidate.sha256,
    candidate.object_key,
    candidate.byte_size,
    candidate.parent_record_id,
    candidate.source_url,
    candidate.reference_month
  from candidates as candidate
  order by candidate.reference_month asc, candidate.created_at asc, candidate.id
  limit requested_limit;
end;
$function$;

create function hr.payroll_unresolved_document_count(
  target_reference_month date
)
returns integer
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  unresolved_count integer;
begin
  if target_reference_month is null
    or target_reference_month < date '2021-01-01'
    or target_reference_month > date '2100-12-01'
    or target_reference_month <> date_trunc('month', target_reference_month)::date
  then
    raise exception 'competencia da folha invalida'
      using errcode = '22023';
  end if;

  select count(distinct document.id)::integer
  into unresolved_count
  from raw.raw_artifacts as document
  join raw.raw_artifacts as parent_artifact
    on parent_artifact.id = document.parent_artifact_id
  join raw.raw_records as record
    on record.raw_artifact_id = parent_artifact.id
  join source.source_endpoints as endpoint
    on endpoint.id = parent_artifact.source_endpoint_id
  join source.data_sources as data_source
    on data_source.id = endpoint.data_source_id
  where document.artifact_kind = 'document'
    and data_source.slug = 'prefeitura-barreiras-transparencia'
    and endpoint.slug = 'dados-abertos-api'
    and document.metadata ->> 'schema_name'
      = 'municipal-transparency-document'
    and document.metadata ->> 'source_record_key' = record.source_record_key
    and document.source_url = record.payload ->> 'url'
    and record.record_type = 'municipal_transparency_servidores'
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
    and (
      record.payload ->> 'tipo' = '1'
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
    and record.payload ->> 'ano_ref' ~ '^(20[2-9][0-9]|2100)$'
    and record.payload ->> 'mes_ref' ~ '^(?:[1-9]|1[0-2])$'
    and make_date(
      (record.payload ->> 'ano_ref')::integer,
      (record.payload ->> 'mes_ref')::integer,
      1
    ) = target_reference_month
    and not exists (
      select 1
      from hr.payroll_report_aggregates as aggregate
      where aggregate.source_document_artifact_id = document.id
        and aggregate.parser_version = 'payroll-report-aggregate/1.3.0'
    );

  return unresolved_count;
end;
$function$;

revoke all on function hr.get_pending_payroll_documents(integer, integer, integer, date)
  from public;
revoke all on function hr.payroll_unresolved_document_count(date) from public;
grant execute on function hr.get_pending_payroll_documents(integer, integer, integer, date)
  to collector_worker;
grant execute on function hr.payroll_unresolved_document_count(date)
  to collector_worker;

comment on function hr.get_pending_payroll_documents(integer, integer, integer, date) is
  'Seleciona para o worker somente PDFs oficiais da folha regular e componentes admitidos, sem ampliar permissoes das aplicacoes publicas.';
comment on function hr.payroll_unresolved_document_count(date) is
  'Conta PDFs oficiais de uma competencia ainda sem agregado na versao vigente, sem expor dados brutos as aplicacoes publicas.';

commit;
