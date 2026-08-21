begin;

create function api.get_public_federal_transfer_source_coverage()
returns table (
  source_key text,
  fiscal_year smallint,
  coverage_status text,
  record_count integer,
  last_attempted_at timestamptz,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
with requested_years as (
  select year_value::smallint as fiscal_year
  from pg_catalog.generate_series(
    2014,
    extract(
      year from pg_catalog.timezone(
        'America/Sao_Paulo',
        pg_catalog.statement_timestamp()
      )
    )::integer
  ) as year_value
), endpoints as (
  select
    source_endpoint.id,
    data_source.slug as source_slug,
    source_endpoint.slug as endpoint_slug,
    source_endpoint.base_url
  from source.source_endpoints as source_endpoint
  join source.data_sources as data_source
    on data_source.id = source_endpoint.data_source_id
  where (data_source.slug, source_endpoint.slug) in (
    ('cgu-portal-transparencia', 'federal-amendments-open-data'),
    ('transferegov-downloads', 'emendas-historicas'),
    ('transferegov-parcerias', 'propostas-barreiras')
  )
), cgu_partition as (
  select partition.*
  from source.collection_partitions as partition
  join endpoints as endpoint
    on endpoint.id = partition.source_endpoint_id
   and endpoint.source_slug = 'cgu-portal-transparencia'
   and endpoint.endpoint_slug = 'federal-amendments-open-data'
  where partition.partition_key =
    'federal-amendments:all-years:barreiras-2903201'
  order by partition.last_attempted_at desc nulls last
  limit 1
), historical_partition as (
  select partition.*
  from source.collection_partitions as partition
  join endpoints as endpoint
    on endpoint.id = partition.source_endpoint_id
   and endpoint.source_slug = 'transferegov-downloads'
   and endpoint.endpoint_slug = 'emendas-historicas'
  where partition.partition_key like 'historical-amendments:%'
  order by partition.last_attempted_at desc nulls last
  limit 1
), cgu_counts as (
  select
    execution.fiscal_year,
    count(*)::integer as record_count
  from territory.cgu_federal_amendment_executions as execution
  group by execution.fiscal_year
), historical_counts as (
  select
    amendment.fiscal_year,
    count(*)::integer as record_count
  from territory.historical_parliamentary_amendments as amendment
  group by amendment.fiscal_year
), current_partitions as (
  select
    requested.fiscal_year,
    partition.status,
    partition.last_attempted_at
  from requested_years as requested
  join endpoints as endpoint
    on endpoint.source_slug = 'transferegov-parcerias'
   and endpoint.endpoint_slug = 'propostas-barreiras'
  left join source.collection_partitions as partition
    on partition.source_endpoint_id = endpoint.id
   and partition.partition_key = 'fiscal-year:' || requested.fiscal_year::text
  where requested.fiscal_year >= 2021
), current_counts as (
  select
    transfer.fiscal_year,
    count(*)::integer as record_count
  from territory.parliamentary_transfers as transfer
  group by transfer.fiscal_year
), cgu_coverage as (
  select
    'cgu_execution'::text as source_key,
    requested.fiscal_year,
    case
      when partition.id is null then 'unclassified'
      when partition.status = 'complete' and coalesce(counts.record_count, 0) > 0
        then 'observed'
      when partition.status in ('complete', 'empty') then 'empty'
      else partition.status
    end::text as coverage_status,
    case
      when partition.status in ('complete', 'empty')
        then coalesce(counts.record_count, 0)
      else null
    end::integer as record_count,
    partition.last_attempted_at,
    endpoint.base_url as source_url
  from requested_years as requested
  cross join endpoints as endpoint
  left join cgu_partition as partition on true
  left join cgu_counts as counts on counts.fiscal_year = requested.fiscal_year
  where endpoint.source_slug = 'cgu-portal-transparencia'
    and endpoint.endpoint_slug = 'federal-amendments-open-data'
    and (
      partition.id is null
      or requested.fiscal_year between
        extract(year from partition.period_start)::smallint and
        extract(year from partition.period_end)::smallint
    )
), historical_coverage as (
  select
    'transferegov_historical'::text as source_key,
    requested.fiscal_year,
    case
      when partition.id is null then 'unclassified'
      when partition.status = 'complete' and coalesce(counts.record_count, 0) > 0
        then 'observed'
      when partition.status in ('complete', 'empty') then 'empty'
      else partition.status
    end::text as coverage_status,
    case
      when partition.status in ('complete', 'empty')
        then coalesce(counts.record_count, 0)
      else null
    end::integer as record_count,
    partition.last_attempted_at,
    endpoint.base_url as source_url
  from requested_years as requested
  cross join endpoints as endpoint
  left join historical_partition as partition on true
  left join historical_counts as counts
    on counts.fiscal_year = requested.fiscal_year
  where endpoint.source_slug = 'transferegov-downloads'
    and endpoint.endpoint_slug = 'emendas-historicas'
    and (
      partition.id is null
      or requested.fiscal_year between
        extract(year from partition.period_start)::smallint and
        extract(year from partition.period_end)::smallint
    )
), current_coverage as (
  select
    'transferegov_current'::text as source_key,
    partition.fiscal_year,
    case
      when partition.status is null then 'unclassified'
      when partition.status = 'complete' and coalesce(counts.record_count, 0) > 0
        then 'observed'
      when partition.status in ('complete', 'empty') then 'empty'
      else partition.status
    end::text as coverage_status,
    case
      when partition.status in ('complete', 'empty')
        then coalesce(counts.record_count, 0)
      else null
    end::integer as record_count,
    partition.last_attempted_at,
    endpoint.base_url as source_url
  from current_partitions as partition
  cross join endpoints as endpoint
  left join current_counts as counts
    on counts.fiscal_year = partition.fiscal_year
  where endpoint.source_slug = 'transferegov-parcerias'
    and endpoint.endpoint_slug = 'propostas-barreiras'
)
select
  coverage.source_key,
  coverage.fiscal_year,
  coverage.coverage_status,
  coverage.record_count,
  coverage.last_attempted_at,
  coverage.source_url,
  'federal-transfer-source-coverage/1.0.0'::text as methodology_version
from (
  select * from cgu_coverage
  union all
  select * from historical_coverage
  union all
  select * from current_coverage
) as coverage
order by coverage.fiscal_year desc, coverage.source_key;
$function$;

revoke all on function api.get_public_federal_transfer_source_coverage()
from public;
grant execute on function api.get_public_federal_transfer_source_coverage()
to anon, authenticated;

comment on function api.get_public_federal_transfer_source_coverage() is
  'Cobertura anual sanitizada das tres series federais; linha ausente na fonte nao equivale a valor financeiro zero.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:public-federal-transfer-source-coverage',
  'methodology.federal_transfer_source_coverage_published',
  'api.get_public_federal_transfer_source_coverage',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'federal-transfer-source-coverage/1.0.0',
    'source_keys', jsonb_build_array(
      'cgu_execution',
      'transferegov_historical',
      'transferegov_current'
    )
  ),
  jsonb_build_object(
    'publishes_aggregate_counts_only', true,
    'publishes_checkpoints', false,
    'publishes_errors', false,
    'publishes_personal_identifiers', false
  )
);

notify pgrst, 'reload schema';

commit;
