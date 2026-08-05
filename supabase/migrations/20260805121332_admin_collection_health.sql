begin;

create index if not exists collection_partitions_latest_idx
  on source.collection_partitions (
    source_endpoint_id,
    last_attempted_at desc,
    id desc
  );

drop function if exists api.get_collection_health(integer);

create function api.get_collection_health(
  page_size integer default 200
)
returns table (
  endpoint_id uuid,
  source_slug text,
  source_name text,
  source_status text,
  endpoint_slug text,
  endpoint_kind text,
  endpoint_enabled boolean,
  latest_partition_key text,
  latest_partition_status text,
  latest_period_start date,
  latest_period_end date,
  latest_expected_records integer,
  latest_observed_records integer,
  latest_attempted_at timestamptz,
  latest_completed_at timestamptz,
  latest_run_status text,
  latest_collector_version text,
  complete_partitions bigint,
  empty_partitions bigint,
  partial_partitions bigint,
  failed_partitions bigint,
  blocked_partitions bigint,
  unresolved_failures bigint,
  latest_failure_status text,
  latest_failure_type text,
  latest_failure_detail text,
  latest_failure_attempt_count integer,
  latest_failure_retryable boolean,
  latest_failure_next_retry_at timestamptz,
  latest_failure_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 500 then
    raise exception 'page_size deve estar entre 1 e 500'
      using errcode = '22023';
  end if;

  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  with partition_totals as (
    select
      partition.source_endpoint_id,
      count(*) filter (where partition.status = 'complete')::bigint
        as complete_partitions,
      count(*) filter (where partition.status = 'empty')::bigint
        as empty_partitions,
      count(*) filter (where partition.status = 'partial')::bigint
        as partial_partitions,
      count(*) filter (where partition.status = 'failed')::bigint
        as failed_partitions,
      count(*) filter (where partition.status = 'blocked')::bigint
        as blocked_partitions
    from source.collection_partitions as partition
    group by partition.source_endpoint_id
  ),
  failure_totals as (
    select
      failure.source_endpoint_id,
      count(*) filter (where failure.status <> 'resolved')::bigint
        as unresolved_failures
    from source.collection_failures as failure
    group by failure.source_endpoint_id
  )
  select
    endpoint.id,
    data_source.slug,
    data_source.name,
    data_source.status,
    endpoint.slug,
    endpoint.endpoint_kind,
    endpoint.enabled,
    latest_partition.partition_key,
    latest_partition.status,
    latest_partition.period_start,
    latest_partition.period_end,
    latest_partition.expected_records,
    latest_partition.observed_records,
    latest_partition.last_attempted_at,
    latest_partition.completed_at,
    latest_run.status,
    latest_run.collector_version,
    coalesce(partition_totals.complete_partitions, 0),
    coalesce(partition_totals.empty_partitions, 0),
    coalesce(partition_totals.partial_partitions, 0),
    coalesce(partition_totals.failed_partitions, 0),
    coalesce(partition_totals.blocked_partitions, 0),
    coalesce(failure_totals.unresolved_failures, 0),
    latest_failure.status,
    latest_failure.error_type,
    latest_failure.error_detail,
    latest_failure.attempt_count,
    latest_failure.retryable,
    latest_failure.next_retry_at,
    latest_failure.failed_at,
    'collection-health/1.0.0'::text
  from source.source_endpoints as endpoint
  join source.data_sources as data_source
    on data_source.id = endpoint.data_source_id
  left join lateral (
    select partition.*
    from source.collection_partitions as partition
    where partition.source_endpoint_id = endpoint.id
    order by partition.last_attempted_at desc, partition.id desc
    limit 1
  ) as latest_partition on true
  left join source.collection_runs as latest_run
    on latest_run.id = latest_partition.collection_run_id
  left join partition_totals
    on partition_totals.source_endpoint_id = endpoint.id
  left join failure_totals
    on failure_totals.source_endpoint_id = endpoint.id
  left join lateral (
    select failure.*
    from source.collection_failures as failure
    where failure.source_endpoint_id = endpoint.id
      and failure.status <> 'resolved'
    order by failure.failed_at desc, failure.id desc
    limit 1
  ) as latest_failure on true
  where endpoint.enabled
  order by
    case
      when latest_partition.status in ('failed', 'blocked') then 0
      when latest_partition.status = 'partial' then 1
      when coalesce(failure_totals.unresolved_failures, 0) > 0 then 2
      when latest_partition.id is null then 3
      else 4
    end,
    data_source.name,
    endpoint.slug
  limit page_size;
end;
$function$;

revoke all on function api.get_collection_health(integer)
  from public, anon;
grant execute on function api.get_collection_health(integer)
  to authenticated;

comment on function api.get_collection_health(integer) is
  'Diagnóstico interno e sanitizado de cobertura e falhas por endpoint, restrito a revisores ativos.';

notify pgrst, 'reload schema';

commit;
