begin;

-- A cobertura diária pública varria os 44 mil artefatos de documento da
-- plataforma (hash semi-join, ~70 MB lidos do disco a cada chamada) para
-- achar os documentos das ~340 edições do Querido Diário; sob a carga do
-- OCR, api.get_public_querido_diario_coverage passava dos 3 s do papel
-- anônimo na janela da sonda pública. Agora cada edição busca os seus
-- documentos pelo índice da chave de origem. Mesmo resultado (conferido em
-- 09/10/2026: 2.106 dias, 813 edições, 1.142 documentos); 0,6-2,9 s -> 0,13 s.
create index if not exists raw_artifacts_document_source_record_key_idx
  on raw.raw_artifacts ((metadata ->> 'source_record_key'))
  where artifact_kind = 'document';

create or replace view source.querido_diario_daily_coverage
with (security_invoker = true)
as
with gazette_records as (
  select (record.payload ->> 'date')::date as published_day,
    record.source_record_key
  from raw.raw_records as record
  where record.record_type = 'querido_diario_gazette'
), documents as (
  select gazette_records.source_record_key, document.id
  from gazette_records
  join lateral (
    -- offset 0 mantém a busca por edição (o planejador estimava 22 mil
    -- linhas e voltava à varredura completa).
    select artifact.id
    from raw.raw_artifacts as artifact
    where artifact.artifact_kind = 'document'
      and artifact.metadata ->> 'source_record_key' = gazette_records.source_record_key
    offset 0
  ) as document on true
), direct_editions as (
  select distinct version.edition_date as published_day,
    version.edition,
    version.raw_artifact_id
  from editorial.gazette_document_versions as version
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
    and version.edition_date is not null
), runs as (
  select run.collection_window_start::date as window_start,
    run.collection_window_end::date as window_end,
    run.status
  from source.collection_runs as run
  join source.source_endpoints as endpoint on endpoint.id = run.source_endpoint_id
  join source.data_sources as data_source on data_source.id = endpoint.data_source_id
  where data_source.slug = 'querido-diario'
), bounds as (
  select
    least(
      (select min(runs.window_start) from runs),
      (select min(gazette_records_1.published_day) from gazette_records as gazette_records_1),
      (select min(direct_editions_1.published_day) from direct_editions as direct_editions_1)
    ) as first_day,
    greatest(
      (select max(runs.window_end) from runs),
      (select max(gazette_records_1.published_day) from gazette_records as gazette_records_1),
      (select max(direct_editions_1.published_day) from direct_editions as direct_editions_1)
    ) as last_day
), days as (
  select generate_series(bounds.first_day::timestamptz, bounds.last_day::timestamptz,
    '1 day'::interval)::date as day
  from bounds
  where bounds.first_day is not null and bounds.last_day is not null
)
select days.day,
  (exists (
    select 1 from runs
    where runs.status = 'succeeded'
      and runs.window_start is not null
      and runs.window_end is not null
      and days.day >= runs.window_start
      and days.day <= runs.window_end
  )) as attempted_by_recorded_window,
  (count(distinct gazette_records.source_record_key)
    + count(distinct direct_editions.edition))::bigint as preserved_editions,
  (count(distinct documents.id)
    + count(distinct direct_editions.raw_artifact_id))::bigint as preserved_documents
from days
left join gazette_records on gazette_records.published_day = days.day
left join documents on documents.source_record_key = gazette_records.source_record_key
left join direct_editions on direct_editions.published_day = days.day
group by days.day
order by days.day;

commit;
