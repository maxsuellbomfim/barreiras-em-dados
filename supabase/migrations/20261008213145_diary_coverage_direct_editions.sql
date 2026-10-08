begin;

-- A classificação diária pública contava só as edições da API do Querido
-- Diário; desde julho de 2026 a Prefeitura publica em plataforma nova e as
-- edições chegam pelo coletor direto (PDF oficial). Em 08/10/2026, 42 dias
-- de julho a setembro apareciam ao público como "0 edições" com edição
-- direta preservada, e a série parava em 28/09 enquanto a edição mais
-- recente era de 07/10. O dia passa a contar as edições de qualquer origem
-- (API ou PDF direto, datadas pelo documento integral) e o dia com edição
-- preservada é "complete" mesmo sem janela da API.
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

create or replace function api.get_public_querido_diario_coverage(
  page_size integer default 31,
  page_offset integer default 0
)
returns table (
  coverage_day date,
  coverage_status text,
  preserved_editions bigint,
  preserved_documents bigint
)
language plpgsql stable security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 366 then
    raise exception 'page_size deve estar entre 1 e 366' using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 5000 then
    raise exception 'page_offset deve estar entre 0 e 5000' using errcode = '22023';
  end if;

  return query
  select coverage.day,
    case
      -- Edição preservada (API ou PDF direto) classifica o dia, com ou
      -- sem janela registrada pela API complementar.
      when coverage.preserved_editions > 0 then 'complete'
      when coverage.attempted_by_recorded_window then 'empty'
      else 'unclassified'
    end,
    coverage.preserved_editions,
    coverage.preserved_documents
  from source.querido_diario_daily_coverage as coverage
  order by coverage.day desc
  limit page_size offset page_offset;
end;
$function$;

comment on function api.get_public_querido_diario_coverage(integer, integer) is
  'Resumo público dos dias do Diário: edições preservadas pela API do Querido Diário ou pelo PDF oficial direto; não confunde dia não classificado com dia vazio.';

notify pgrst, 'reload schema';

commit;
