begin;

create or replace function hr.verify_payroll_report_aggregate_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  origin_record raw.raw_records%rowtype;
  source_document raw.raw_artifacts%rowtype;
  source_year text;
  source_month text;
  normalized_title text;
  origin_source_slug text;
  origin_endpoint_slug text;
  origin_endpoint_id uuid;
begin
  select * into origin_record
  from raw.raw_records
  where id = new.origin_raw_record_id;

  select * into source_document
  from raw.raw_artifacts
  where id = new.source_document_artifact_id;

  select data_source.slug, endpoint.slug, endpoint.id
  into origin_source_slug, origin_endpoint_slug, origin_endpoint_id
  from raw.raw_artifacts as origin_artifact
  join source.source_endpoints as endpoint
    on endpoint.id = origin_artifact.source_endpoint_id
  join source.data_sources as data_source
    on data_source.id = endpoint.data_source_id
  where origin_artifact.id = origin_record.raw_artifact_id;

  normalized_title := regexp_replace(
    btrim(translate(
      normalize(lower(coalesce(origin_record.payload ->> 'titulo', '')), NFKD),
      U&'\0300\0301\0302\0303\0308\0327',
      ''
    )),
    '[[:space:]]+',
    ' ',
    'g'
  );

  if origin_record.id is null
    or origin_source_slug is distinct from 'prefeitura-barreiras-transparencia'
    or origin_endpoint_slug is distinct from 'dados-abertos-api'
    or origin_record.record_type <> 'municipal_transparency_servidores'
    or not (
      (
        origin_record.payload ->> 'tipo' = '1'
        and normalized_title in (
          'relacao de servidores',
          'relacao servidores',
          'relacao de servidores 13o salario'
        )
      )
      or (
        coalesce(trim(origin_record.payload ->> 'tipo'), '') = ''
        and normalized_title = 'relacao de servidores'
      )
    ) then
    raise exception 'payroll aggregate requires an official municipal staff catalog record'
      using errcode = '23514';
  end if;

  source_year := origin_record.payload ->> 'ano_ref';
  source_month := origin_record.payload ->> 'mes_ref';
  if source_year is null or source_year !~ '^(20[2-9][0-9]|2100)$'
    or source_month is null or source_month !~ '^(?:[1-9]|1[0-2])$'
    or make_date(source_year::integer, source_month::integer, 1)
      <> new.reference_month then
    raise exception 'payroll aggregate reference month differs from official catalog'
      using errcode = '23514';
  end if;

  if source_document.id is null
    or source_document.artifact_kind <> 'document'
    or source_document.source_endpoint_id is distinct from origin_endpoint_id
    or source_document.metadata ->> 'schema_name'
      <> 'municipal-transparency-document'
    or source_document.metadata ->> 'source_record_key'
      is distinct from origin_record.source_record_key
    or source_document.source_url
      is distinct from origin_record.payload ->> 'url' then
    raise exception 'payroll aggregate document does not match official catalog evidence'
      using errcode = '23514';
  end if;

  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_aggregate_lineage() from public;

alter table hr.payroll_report_aggregate_invalidations
  drop constraint payroll_report_invalidations_reason_allowed;

alter table hr.payroll_report_aggregate_invalidations
  add constraint payroll_report_invalidations_reason_allowed
  check (reason_code in (
    'mixed_payroll_cycle_header',
    'non_staff_catalog_title',
    'missing_staff_catalog_title',
    'mismatched_source_endpoint'
  ));

insert into hr.payroll_report_aggregate_invalidations (
  aggregate_id,
  evidence_artifact_id,
  reason_code,
  invalidator_version,
  details,
  invalidated_at
)
select
  aggregate.id,
  document.id,
  case
    when regexp_replace(
      btrim(translate(
        normalize(lower(coalesce(record.payload ->> 'titulo', '')), NFKD),
        U&'\0300\0301\0302\0303\0308\0327',
        ''
      )),
      '[[:space:]]+', ' ', 'g'
    ) = '' then 'missing_staff_catalog_title'
    else 'non_staff_catalog_title'
  end,
  'payroll-title-invalidation/1.0.0',
  jsonb_build_object(
    'source_title', record.payload ->> 'titulo',
    'source_type', record.payload ->> 'tipo',
    'parser_version', aggregate.parser_version,
    'artifact_sha256', document.sha256
  ),
  statement_timestamp()
from hr.payroll_report_aggregates as aggregate
join raw.raw_records as record
  on record.id = aggregate.origin_raw_record_id
join raw.raw_artifacts as document
  on document.id = aggregate.source_document_artifact_id
join raw.raw_artifacts as origin_artifact
  on origin_artifact.id = record.raw_artifact_id
join source.source_endpoints as endpoint
  on endpoint.id = origin_artifact.source_endpoint_id
join source.data_sources as data_source
  on data_source.id = endpoint.data_source_id
where record.record_type = 'municipal_transparency_servidores'
  and data_source.slug = 'prefeitura-barreiras-transparencia'
  and endpoint.slug = 'dados-abertos-api'
  and not (
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
on conflict (aggregate_id) do nothing;

insert into hr.payroll_report_aggregate_invalidations (
  aggregate_id,
  evidence_artifact_id,
  reason_code,
  invalidator_version,
  details,
  invalidated_at
)
select
  aggregate.id,
  document.id,
  'mismatched_source_endpoint',
  'payroll-title-invalidation/1.0.0',
  jsonb_build_object(
    'catalog_endpoint_id', origin_artifact.source_endpoint_id,
    'document_endpoint_id', document.source_endpoint_id,
    'parser_version', aggregate.parser_version,
    'artifact_sha256', document.sha256
  ),
  statement_timestamp()
from hr.payroll_report_aggregates as aggregate
join raw.raw_records as record
  on record.id = aggregate.origin_raw_record_id
join raw.raw_artifacts as origin_artifact
  on origin_artifact.id = record.raw_artifact_id
join raw.raw_artifacts as document
  on document.id = aggregate.source_document_artifact_id
join source.source_endpoints as endpoint
  on endpoint.id = origin_artifact.source_endpoint_id
join source.data_sources as data_source
  on data_source.id = endpoint.data_source_id
where data_source.slug = 'prefeitura-barreiras-transparencia'
  and endpoint.slug = 'dados-abertos-api'
  and document.source_endpoint_id is distinct from origin_artifact.source_endpoint_id
on conflict (aggregate_id) do nothing;

comment on function hr.verify_payroll_report_aggregate_lineage() is
  'Valida fonte, endpoint, competência, documento e natureza da folha. Tipo 1 só é aceito com título oficial de servidores; títulos ausentes, estagiários e terceirizados são rejeitados mesmo quando a fonte informa tipo incorreto.';

commit;
