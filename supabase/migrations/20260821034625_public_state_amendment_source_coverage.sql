begin;

create function api.get_public_state_amendment_source_coverage()
returns table (
  fiscal_year smallint,
  loa_status text,
  amendment_count integer,
  author_count integer,
  authorized_amount numeric(20,2),
  execution_status text,
  matched_count integer,
  ambiguous_count integer,
  not_found_count integer,
  unavailable_scope_count integer,
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
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
    2021,
    extract(
      year from pg_catalog.timezone(
        'America/Sao_Paulo',
        pg_catalog.statement_timestamp()
      )
    )::integer
  ) as year_value
), endpoint as (
  select source_endpoint.id, source_endpoint.base_url
  from source.source_endpoints as source_endpoint
  join source.data_sources as data_source
    on data_source.id = source_endpoint.data_source_id
  where data_source.slug = 'bahia-seplan-budget'
    and source_endpoint.slug = 'state-loa-amendment-annexes'
), latest_partition as (
  select distinct on (
    extract(year from collection_partition.period_start)
  )
    extract(year from collection_partition.period_start)::smallint
      as fiscal_year,
    collection_partition.status,
    collection_partition.last_attempted_at
  from source.collection_partitions as collection_partition
  join endpoint
    on endpoint.id = collection_partition.source_endpoint_id
  where collection_partition.partition_key = concat(
    'loa-annex:',
    extract(year from collection_partition.period_start)::integer
  )
  order by
    extract(year from collection_partition.period_start),
    collection_partition.last_attempted_at desc,
    collection_partition.updated_at desc
), amendment_totals as (
  select
    amendment.fiscal_year,
    count(*)::integer as amendment_count,
    count(distinct amendment.author_key)::integer as author_count,
    sum(amendment.authorized_amount)::numeric(20,2) as authorized_amount
  from territory.bahia_state_loa_amendments as amendment
  group by amendment.fiscal_year
), execution_totals as (
  select
    reconciliation.fiscal_year,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::integer as matched_count,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_non_unique_loa_key',
        'blocked_non_unique_execution_key'
      )
    )::integer as ambiguous_count,
    count(*) filter (
      where reconciliation.reconciliation_status =
        'not_found_in_execution_source'
    )::integer as not_found_count,
    count(*) filter (
      where reconciliation.reconciliation_status in (
        'blocked_scope_year_not_indexed',
        'blocked_scope_not_collected'
      )
    )::integer as unavailable_scope_count,
    sum(reconciliation.committed_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2) as committed_amount,
    sum(reconciliation.liquidated_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2) as liquidated_amount,
    sum(reconciliation.paid_amount) filter (
      where reconciliation.reconciliation_status =
        'matched_bidirectional_unique'
    )::numeric(20,2) as paid_amount
  from territory.bahia_state_loa_execution_reconciliation as reconciliation
  group by reconciliation.fiscal_year
), classified as (
  select
    requested.fiscal_year,
    case
      when partition.status in ('complete', 'empty')
        and coalesce(amendment.amendment_count, 0) > 0 then 'observed'
      when partition.status in ('complete', 'empty') then 'empty'
      when partition.status is null then 'unclassified'
      else partition.status
    end::text as loa_status,
    amendment.amendment_count,
    amendment.author_count,
    amendment.authorized_amount,
    execution.matched_count,
    execution.ambiguous_count,
    execution.not_found_count,
    execution.unavailable_scope_count,
    execution.committed_amount,
    execution.liquidated_amount,
    execution.paid_amount,
    partition.last_attempted_at,
    endpoint.base_url as source_url
  from requested_years as requested
  cross join endpoint
  left join latest_partition as partition
    on partition.fiscal_year = requested.fiscal_year
  left join amendment_totals as amendment
    on amendment.fiscal_year = requested.fiscal_year
  left join execution_totals as execution
    on execution.fiscal_year = requested.fiscal_year
)
select
  classified.fiscal_year,
  classified.loa_status,
  case
    when classified.loa_status = 'observed' then classified.amendment_count
    when classified.loa_status = 'empty' then 0
    else null
  end::integer as amendment_count,
  case
    when classified.loa_status = 'observed' then classified.author_count
    when classified.loa_status = 'empty' then 0
    else null
  end::integer as author_count,
  case when classified.loa_status = 'observed'
    then classified.authorized_amount end::numeric(20,2) as authorized_amount,
  case
    when classified.loa_status <> 'observed' then 'loa_unavailable'
    when coalesce(classified.matched_count, 0) > 0
      and coalesce(classified.ambiguous_count, 0) = 0
      and coalesce(classified.not_found_count, 0) = 0
      and coalesce(classified.unavailable_scope_count, 0) = 0
      then 'observed'
    when coalesce(classified.matched_count, 0) > 0
      or coalesce(classified.ambiguous_count, 0) > 0
      or coalesce(classified.not_found_count, 0) > 0
      then 'partial'
    when classified.unavailable_scope_count = classified.amendment_count
      then 'scope_not_indexed'
    else 'unclassified'
  end::text as execution_status,
  case when classified.loa_status = 'observed'
    then classified.matched_count end::integer as matched_count,
  case when classified.loa_status = 'observed'
    then classified.ambiguous_count end::integer as ambiguous_count,
  case when classified.loa_status = 'observed'
    then classified.not_found_count end::integer as not_found_count,
  case when classified.loa_status = 'observed'
    then classified.unavailable_scope_count end::integer
    as unavailable_scope_count,
  case when coalesce(classified.matched_count, 0) > 0
    then classified.committed_amount end::numeric(20,2) as committed_amount,
  case when coalesce(classified.matched_count, 0) > 0
    then classified.liquidated_amount end::numeric(20,2) as liquidated_amount,
  case when coalesce(classified.matched_count, 0) > 0
    then classified.paid_amount end::numeric(20,2) as paid_amount,
  classified.last_attempted_at,
  classified.source_url,
  'state-amendment-source-coverage/1.0.0'::text as methodology_version
from classified
order by classified.fiscal_year desc;
$function$;

revoke all on function api.get_public_state_amendment_source_coverage()
from public;
grant execute on function api.get_public_state_amendment_source_coverage()
to anon, authenticated;

comment on function api.get_public_state_amendment_source_coverage() is
  'Cobertura anual sanitizada dos anexos estaduais e da reconciliacao financeira; ausencia de ligacao conserva valores nulos.';

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
  'migration:public-state-amendment-source-coverage',
  'methodology.state_amendment_source_coverage_published',
  'api.get_public_state_amendment_source_coverage',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'state-amendment-source-coverage/1.0.0',
    'first_fiscal_year', 2021,
    'execution_amounts_require_unique_match', true
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
