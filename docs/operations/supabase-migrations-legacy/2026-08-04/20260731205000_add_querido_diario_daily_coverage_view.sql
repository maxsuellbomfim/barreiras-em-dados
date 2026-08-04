-- Visão interna de lacunas de cobertura da coleta do Querido Diário.
-- Uso operacional (psql/console); não é exposta na Data API nem a perfis
-- anônimos. Cada dia entre a primeira e a última data conhecida mostra se
-- houve execução bem-sucedida com janela registrada cobrindo o dia, quantas
-- edições foram preservadas e quantos documentos filhos existem.
-- Janelas nulas pertencem a execuções anteriores ao registro de janela e
-- aparecem como "não atribuível" (attempted_by_recorded_window = false).

create or replace view source.querido_diario_daily_coverage
with (security_invoker = true)
as
with gazette_records as (
  select
    (record.payload ->> 'date')::date as published_day,
    record.source_record_key
  from raw.raw_records as record
  where record.record_type = 'querido_diario_gazette'
),
documents as (
  select
    artifact.metadata ->> 'source_record_key' as source_record_key,
    artifact.id
  from raw.raw_artifacts as artifact
  where artifact.artifact_kind = 'document'
),
runs as (
  select
    run.collection_window_start::date as window_start,
    run.collection_window_end::date as window_end,
    run.status
  from source.collection_runs as run
  join source.source_endpoints as endpoint
    on endpoint.id = run.source_endpoint_id
  join source.data_sources as data_source
    on data_source.id = endpoint.data_source_id
  where data_source.slug = 'querido-diario'
),
bounds as (
  select
    least(
      (select min(window_start) from runs),
      (select min(published_day) from gazette_records)
    ) as first_day,
    greatest(
      (select max(window_end) from runs),
      (select max(published_day) from gazette_records)
    ) as last_day
),
days as (
  select generate_series(first_day, last_day, interval '1 day')::date as day
  from bounds
  where first_day is not null
    and last_day is not null
)
select
  days.day,
  exists (
    select 1
    from runs
    where runs.status = 'succeeded'
      and runs.window_start is not null
      and runs.window_end is not null
      and days.day between runs.window_start and runs.window_end
  ) as attempted_by_recorded_window,
  count(distinct gazette_records.source_record_key) as preserved_editions,
  count(distinct documents.id) as preserved_documents
from days
left join gazette_records
  on gazette_records.published_day = days.day
left join documents
  on documents.source_record_key = gazette_records.source_record_key
group by days.day
order by days.day;

comment on view source.querido_diario_daily_coverage is
  'Lacunas diárias da coleta do Querido Diário; visão interna operacional.';

revoke all on source.querido_diario_daily_coverage
  from public, anon, authenticated;
