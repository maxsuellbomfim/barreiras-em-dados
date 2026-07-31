begin;

create or replace function api.get_querido_diario_collection_status()
returns table (
  source_slug text,
  source_name text,
  endpoint_slug text,
  latest_status text,
  last_successful_at timestamptz,
  coverage_start date,
  coverage_end date,
  preserved_response_count bigint,
  preserved_edition_count bigint,
  collector_version text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  with selected_endpoint as (
    select
      data_source.id as source_id,
      data_source.slug as source_slug,
      data_source.name as source_name,
      endpoint.id as endpoint_id,
      endpoint.slug as endpoint_slug
    from source.data_sources as data_source
    join source.source_endpoints as endpoint
      on endpoint.data_source_id = data_source.id
    where data_source.slug = 'querido-diario'
      and endpoint.slug = 'gazettes-api'
      and data_source.status = 'active'
      and endpoint.enabled
    limit 1
  ),
  latest_success as (
    select
      collection_run.status,
      collection_run.completed_at,
      collection_run.collector_version
    from source.collection_runs as collection_run
    join selected_endpoint
      on selected_endpoint.endpoint_id = collection_run.source_endpoint_id
    where collection_run.status = 'succeeded'
      and collection_run.completed_at is not null
    order by collection_run.completed_at desc, collection_run.created_at desc
    limit 1
  ),
  preserved_responses as (
    select count(distinct artifact.sha256)::bigint as response_count
    from raw.raw_artifacts as artifact
    join selected_endpoint
      on selected_endpoint.endpoint_id = artifact.source_endpoint_id
    where artifact.artifact_kind = 'http_response'
  ),
  valid_editions as (
    select
      record.source_record_key,
      (record.payload ->> 'date')::date as publication_date
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    join selected_endpoint
      on selected_endpoint.endpoint_id = artifact.source_endpoint_id
    where record.record_type = 'querido_diario_gazette'
      and record.payload ->> 'territory_id' = '2903201'
      and record.payload ->> 'date' ~ '^\d{4}-\d{2}-\d{2}$'
  ),
  edition_coverage as (
    select
      min(valid_editions.publication_date) as coverage_start,
      max(valid_editions.publication_date) as coverage_end,
      count(distinct valid_editions.source_record_key)::bigint as edition_count
    from valid_editions
  )
  select
    selected_endpoint.source_slug,
    selected_endpoint.source_name,
    selected_endpoint.endpoint_slug,
    latest_success.status as latest_status,
    latest_success.completed_at as last_successful_at,
    edition_coverage.coverage_start,
    edition_coverage.coverage_end,
    coalesce(preserved_responses.response_count, 0)::bigint,
    coalesce(edition_coverage.edition_count, 0)::bigint,
    latest_success.collector_version,
    'querido-diario-collection-status/1.0.0'::text
  from selected_endpoint
  left join latest_success on true
  left join preserved_responses on true
  left join edition_coverage on true;
$$;

revoke all on function api.get_querido_diario_collection_status()
  from public;
grant execute on function api.get_querido_diario_collection_status()
  to anon, authenticated;

comment on function api.get_querido_diario_collection_status() is
  'Curated non-reputational aggregate of preserved Querido Diario collection evidence.';

commit;
