begin;

-- A cobertura diária do Querido Diário juntava as edições com TODOS os
-- artefatos de documento da plataforma (TCM, Diário direto, finanças...) pela
-- chave de origem; documentos de outras fontes nunca casam. Restringir aos
-- documentos cuja chave existe nos registros do Querido Diário dá o mesmo
-- resultado (conferido em produção em 08/10/2026: 2.097 dias idênticos nos
-- dois sentidos) e tira a função pública de 5 s, acima do limite de 3 s do
-- papel anon.
create or replace view source.querido_diario_daily_coverage
with (security_invoker = true)
as
with gazette_records as (
  select (record.payload ->> 'date')::date as published_day,
    record.source_record_key
  from raw.raw_records as record
  where record.record_type = 'querido_diario_gazette'
), documents as (
  select artifact.metadata ->> 'source_record_key' as source_record_key,
    artifact.id
  from raw.raw_artifacts as artifact
  where artifact.artifact_kind = 'document'
    and artifact.metadata ->> 'source_record_key' in (
      select gazette_records.source_record_key from gazette_records
    )
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
      (select min(gazette_records_1.published_day) from gazette_records as gazette_records_1)
    ) as first_day,
    greatest(
      (select max(runs.window_end) from runs),
      (select max(gazette_records_1.published_day) from gazette_records as gazette_records_1)
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
  count(distinct gazette_records.source_record_key) as preserved_editions,
  count(distinct documents.id) as preserved_documents
from days
left join gazette_records on gazette_records.published_day = days.day
left join documents on documents.source_record_key = gazette_records.source_record_key
group by days.day
order by days.day;

commit;
