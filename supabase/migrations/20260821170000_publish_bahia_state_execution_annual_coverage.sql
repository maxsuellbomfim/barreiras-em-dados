begin;

create table territory.bahia_state_execution_annual_coverage_snapshot (
  fiscal_year smallint primary key check (fiscal_year between 2021 and 2100),
  source_aggregate_count integer not null check (source_aggregate_count > 0),
  source_author_count integer not null check (source_author_count > 0),
  territorial_key_status text not null default
    'territorial_key_unavailable_in_source'
    check (territorial_key_status = 'territorial_key_unavailable_in_source'),
  source_snapshot_status text not null default 'source_snapshot_observed'
    check (source_snapshot_status = 'source_snapshot_observed'),
  source_url text not null check (source_url ~ '^https://'),
  source_artifact_sha256 text not null
    check (source_artifact_sha256 ~ '^[0-9a-f]{64}$'),
  source_collected_at timestamptz not null,
  extraction_job_id uuid not null references raw.extraction_jobs(id),
  methodology_version text not null default
    'bahia-state-execution-source-coverage/1.0.0'
    check (
      methodology_version = 'bahia-state-execution-source-coverage/1.0.0'
    ),
  refreshed_at timestamptz not null default statement_timestamp()
);

alter table territory.bahia_state_execution_annual_coverage_snapshot
  enable row level security;
alter table territory.bahia_state_execution_annual_coverage_snapshot
  force row level security;

revoke all on territory.bahia_state_execution_annual_coverage_snapshot
  from public, anon, authenticated;

create index extraction_jobs_bahia_state_execution_latest_idx
  on raw.extraction_jobs (updated_at desc, id desc)
  where job_type = 'bahia_state_execution_aggregates_v1'
    and status = 'succeeded';

create index extraction_results_bahia_state_execution_coverage_idx
  on raw.extraction_results (extraction_job_id, id)
  where candidate_type = 'bahia_state_execution_aggregate'
    and extractor_version = 'bahia-state-execution-aggregate/1.0.0'
    and validator_version = 'bahia-state-execution-deterministic/1.0.0'
    and validation_status = 'valid';

create or replace function territory.refresh_bahia_state_execution_annual_coverage_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  latest_job_id uuid;
  latest_artifact_id uuid;
  latest_source_url text;
  latest_artifact_sha256 text;
  latest_collected_at timestamptz;
  expected_count integer;
  valid_count integer;
  inserted_count integer;
begin
  select
    job.id,
    artifact.id,
    artifact.source_url,
    artifact.sha256,
    artifact.retrieved_at
  into
    latest_job_id,
    latest_artifact_id,
    latest_source_url,
    latest_artifact_sha256,
    latest_collected_at
  from raw.extraction_jobs as job
  join raw.raw_artifacts as artifact on artifact.id = job.raw_artifact_id
  where job.job_type = 'bahia_state_execution_aggregates_v1'
    and job.status = 'succeeded'
  order by job.updated_at desc, job.id desc
  limit 1;

  if latest_job_id is null then
    return 0;
  end if;

  select count(*)::integer
  into expected_count
  from raw.extraction_results as result
  where result.extraction_job_id = latest_job_id;

  select count(*)::integer
  into valid_count
  from raw.extraction_results as result
  where result.extraction_job_id = latest_job_id
    and result.candidate_type = 'bahia_state_execution_aggregate'
    and result.extractor_version = 'bahia-state-execution-aggregate/1.0.0'
    and result.validator_version = 'bahia-state-execution-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and result.result_payload ->> 'schema_name'
      = 'bahia-state-execution-aggregate'
    and result.result_payload ->> 'schema_version' = '1.0.0'
    and result.result_payload ->> 'parser_version'
      = 'bahia-state-execution-aggregate/1.0.0'
    and result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
    and (result.result_payload ->> 'fiscal_year')::integer between 2000 and 2100
    and nullif(btrim(result.result_payload ->> 'author_external_code'), '')
      is not null
    and result.result_payload ->> 'territorial_scope'
      = 'not_available_in_execution_archive'
    and result.result_payload ->> 'source_url' ~ '^https://'
    and result.result_payload ->> 'source_artifact_sha256'
      ~ '^[0-9a-f]{64}$'
    and result.result_payload ->> 'source_artifact_sha256'
      = latest_artifact_sha256
    and nullif(btrim(result.result_payload ->> 'source_collected_at'), '')
      is not null;

  if expected_count = 0 or valid_count <> expected_count then
    raise exception using
      errcode = '23514',
      message = 'Latest Bahia state execution snapshot failed coverage validation',
      detail = format(
        'job=%s artifact=%s expected=%s valid=%s',
        latest_job_id,
        latest_artifact_id,
        expected_count,
        valid_count
      );
  end if;

  if not exists (
    select 1
    from raw.extraction_results as result
    where result.extraction_job_id = latest_job_id
      and (result.result_payload ->> 'fiscal_year')::integer between 2021
        and extract(year from latest_collected_at)::integer
  ) then
    raise exception using
      errcode = '23514',
      message = 'Latest Bahia state execution snapshot has no public-period rows';
  end if;

  delete from territory.bahia_state_execution_annual_coverage_snapshot;

  insert into territory.bahia_state_execution_annual_coverage_snapshot (
    fiscal_year,
    source_aggregate_count,
    source_author_count,
    source_url,
    source_artifact_sha256,
    source_collected_at,
    extraction_job_id,
    refreshed_at
  )
  select
    (result.result_payload ->> 'fiscal_year')::smallint,
    count(*)::integer,
    count(distinct btrim(
      result.result_payload ->> 'author_external_code'
    ))::integer,
    latest_source_url,
    latest_artifact_sha256,
    latest_collected_at,
    latest_job_id,
    statement_timestamp()
  from raw.extraction_results as result
  where result.extraction_job_id = latest_job_id
    and (result.result_payload ->> 'fiscal_year')::integer between 2021
      and extract(year from latest_collected_at)::integer
  group by (result.result_payload ->> 'fiscal_year')::smallint;

  get diagnostics inserted_count = row_count;
  return inserted_count;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_execution_annual_coverage_snapshot()
  from public, anon, authenticated;

create or replace function territory.refresh_bahia_state_execution_coverage_on_insert()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (
    select 1
    from inserted_results as result
    where result.candidate_type = 'bahia_state_execution_aggregate'
  ) then
    perform territory.refresh_bahia_state_execution_annual_coverage_snapshot();
  end if;
  return null;
end;
$$;

revoke all on function
  territory.refresh_bahia_state_execution_coverage_on_insert()
  from public, anon, authenticated;

create trigger extraction_results_refresh_bahia_state_execution_coverage
after insert on raw.extraction_results
referencing new table as inserted_results
for each statement
execute function territory.refresh_bahia_state_execution_coverage_on_insert();

create or replace function api.get_public_bahia_state_execution_annual_coverage()
returns table (
  fiscal_year smallint,
  source_aggregate_count integer,
  source_author_count integer,
  territorial_key_status text,
  source_snapshot_status text,
  source_url text,
  source_artifact_sha256 text,
  source_collected_at timestamptz,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    snapshot.fiscal_year,
    snapshot.source_aggregate_count,
    snapshot.source_author_count,
    snapshot.territorial_key_status,
    snapshot.source_snapshot_status,
    snapshot.source_url,
    snapshot.source_artifact_sha256,
    snapshot.source_collected_at,
    snapshot.methodology_version
  from territory.bahia_state_execution_annual_coverage_snapshot as snapshot
  order by snapshot.fiscal_year desc;
$$;

revoke all on function
  api.get_public_bahia_state_execution_annual_coverage()
  from public;
grant execute on function
  api.get_public_bahia_state_execution_annual_coverage()
  to anon, authenticated;

select territory.refresh_bahia_state_execution_annual_coverage_snapshot();

commit;
