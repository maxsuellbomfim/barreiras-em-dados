begin;

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create schema if not exists source;
create schema if not exists raw;
create schema if not exists org;
create schema if not exists hr;
create schema if not exists procurement;
create schema if not exists finance;
create schema if not exists evidence;
create schema if not exists analysis;
create schema if not exists editorial;
create schema if not exists audit;
create schema if not exists api;

revoke create on schema public from public;
revoke all on schema
  source,
  raw,
  org,
  hr,
  procurement,
  finance,
  evidence,
  analysis,
  editorial,
  audit
from public;

do $$
declare
  role_name text;
  schema_name text;
begin
  foreach role_name in array array['anon', 'authenticated']
  loop
    if exists (select 1 from pg_roles where rolname = role_name) then
      foreach schema_name in array array[
        'source', 'raw', 'org', 'hr', 'procurement', 'finance',
        'evidence', 'analysis', 'editorial', 'audit'
      ]
      loop
        execute format('revoke all on schema %I from %I', schema_name, role_name);
      end loop;

      execute format('grant usage on schema api to %I', role_name);
    end if;
  end loop;
end
$$;

create or replace function audit.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = statement_timestamp();
  return new;
end;
$$;

create or replace function audit.reject_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'immutable relation %.% does not allow %',
    tg_table_schema,
    tg_table_name,
    tg_op
    using errcode = '55000';
end;
$$;

create table source.data_sources (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  name text not null check (length(btrim(name)) > 0),
  description text,
  authority_level text not null check (
    authority_level in ('official', 'official_aggregator', 'oversight_body', 'secondary')
  ),
  is_official boolean not null default false,
  homepage_url text not null check (homepage_url ~ '^https://'),
  terms_url text check (terms_url is null or terms_url ~ '^https://'),
  documentation_url text check (documentation_url is null or documentation_url ~ '^https://'),
  status text not null default 'active' check (
    status in ('active', 'degraded', 'paused', 'retired')
  ),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp()
);

create trigger data_sources_set_updated_at
before update on source.data_sources
for each row execute function audit.set_updated_at();

create table source.source_endpoints (
  id uuid primary key default gen_random_uuid(),
  data_source_id uuid not null references source.data_sources(id),
  slug text not null check (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
  endpoint_kind text not null check (
    endpoint_kind in ('api', 'html', 'rss', 'file', 'database_export')
  ),
  base_url text not null check (base_url ~ '^https://'),
  http_method text not null default 'GET' check (http_method in ('GET', 'HEAD')),
  rate_limit_per_minute integer check (rate_limit_per_minute is null or rate_limit_per_minute > 0),
  request_timeout_seconds integer not null default 30 check (
    request_timeout_seconds between 1 and 300
  ),
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb check (
    jsonb_typeof(config) = 'object'
    and not (config ?| array['password', 'secret', 'token', 'api_key', 'service_role_key'])
  ),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  unique (data_source_id, slug)
);

create trigger source_endpoints_set_updated_at
before update on source.source_endpoints
for each row execute function audit.set_updated_at();

create table source.collection_runs (
  id uuid primary key default gen_random_uuid(),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  idempotency_key text not null unique check (length(idempotency_key) between 16 and 256),
  collector_version text not null check (length(btrim(collector_version)) > 0),
  parser_version text not null default 'not-applicable',
  collection_window_start timestamptz,
  collection_window_end timestamptz,
  cursor_before jsonb,
  cursor_after jsonb,
  status text not null default 'queued' check (
    status in (
      'queued', 'running', 'succeeded', 'partial', 'retry_scheduled',
      'failed', 'dead_lettered', 'cancelled'
    )
  ),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  metrics jsonb not null default '{}'::jsonb check (jsonb_typeof(metrics) = 'object'),
  error_code text,
  error_detail text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (
    collection_window_start is null
    or collection_window_end is null
    or collection_window_start <= collection_window_end
  ),
  check (
    completed_at is null
    or started_at is null
    or completed_at >= started_at
  )
);

create index collection_runs_endpoint_status_idx
  on source.collection_runs (source_endpoint_id, status, created_at desc);

create trigger collection_runs_set_updated_at
before update on source.collection_runs
for each row execute function audit.set_updated_at();

create table raw.raw_artifacts (
  id uuid primary key default gen_random_uuid(),
  collection_run_id uuid not null references source.collection_runs(id),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  parent_artifact_id uuid references raw.raw_artifacts(id),
  idempotency_key text not null unique check (length(idempotency_key) between 16 and 256),
  artifact_kind text not null check (
    artifact_kind in ('http_response', 'document', 'attachment', 'archive', 'page_image')
  ),
  source_url text not null check (source_url ~ '^https://'),
  retrieved_at timestamptz not null,
  source_published_at timestamptz,
  source_last_modified_at timestamptz,
  source_etag text,
  http_status smallint check (http_status is null or http_status between 100 and 599),
  content_type text,
  byte_size bigint not null check (byte_size >= 0),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  object_key text not null unique check (length(btrim(object_key)) > 0),
  collector_version text not null,
  parser_version text not null default 'not-applicable',
  response_headers jsonb not null default '{}'::jsonb check (
    jsonb_typeof(response_headers) = 'object'
    and not (response_headers ?| array['authorization', 'cookie', 'set-cookie'])
  ),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default statement_timestamp()
);

create index raw_artifacts_sha256_idx on raw.raw_artifacts (sha256);
create index raw_artifacts_source_time_idx
  on raw.raw_artifacts (source_endpoint_id, retrieved_at desc);

create table raw.raw_records (
  id uuid primary key default gen_random_uuid(),
  raw_artifact_id uuid not null references raw.raw_artifacts(id),
  source_record_key text,
  record_type text not null check (length(btrim(record_type)) > 0),
  record_index integer not null check (record_index >= 0),
  payload jsonb not null,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  parser_version text not null,
  idempotency_key text not null unique check (length(idempotency_key) between 16 and 256),
  collected_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (raw_artifact_id, record_index)
);

create index raw_records_source_key_idx
  on raw.raw_records (record_type, source_record_key)
  where source_record_key is not null;

create table raw.document_pages (
  id uuid primary key default gen_random_uuid(),
  raw_artifact_id uuid not null references raw.raw_artifacts(id),
  page_number integer not null check (page_number > 0),
  parser_version text not null,
  extraction_method text not null check (
    extraction_method in ('embedded_text', 'ocr', 'hybrid', 'manual')
  ),
  text_content text,
  text_sha256 text check (text_sha256 is null or text_sha256 ~ '^[0-9a-f]{64}$'),
  image_artifact_id uuid references raw.raw_artifacts(id),
  dimensions jsonb,
  created_at timestamptz not null default statement_timestamp(),
  unique (raw_artifact_id, page_number, parser_version)
);

create table raw.extraction_jobs (
  id uuid primary key default gen_random_uuid(),
  raw_artifact_id uuid references raw.raw_artifacts(id),
  raw_record_id uuid references raw.raw_records(id),
  job_type text not null,
  idempotency_key text not null unique check (length(idempotency_key) between 16 and 256),
  status text not null default 'queued' check (
    status in ('queued', 'running', 'retry_scheduled', 'succeeded', 'failed', 'dead_lettered')
  ),
  priority smallint not null default 0,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 5 check (max_attempts between 1 and 100),
  available_at timestamptz not null default statement_timestamp(),
  leased_until timestamptz,
  worker_id text,
  last_error_code text,
  last_error_detail text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (num_nonnulls(raw_artifact_id, raw_record_id) = 1)
);

create index extraction_jobs_claim_idx
  on raw.extraction_jobs (priority desc, available_at, created_at)
  where status in ('queued', 'retry_scheduled');

create trigger extraction_jobs_set_updated_at
before update on raw.extraction_jobs
for each row execute function audit.set_updated_at();

create table raw.extraction_results (
  id uuid primary key default gen_random_uuid(),
  extraction_job_id uuid not null references raw.extraction_jobs(id),
  supersedes_id uuid references raw.extraction_results(id),
  candidate_type text not null,
  extractor_version text not null,
  validator_version text not null,
  result_payload jsonb not null,
  confidence numeric(6,5) check (confidence is null or confidence between 0 and 1),
  validation_status text not null check (
    validation_status in ('valid', 'invalid', 'needs_review')
  ),
  validation_errors jsonb not null default '[]'::jsonb check (
    jsonb_typeof(validation_errors) = 'array'
  ),
  created_at timestamptz not null default statement_timestamp()
);

create index extraction_results_job_idx
  on raw.extraction_results (extraction_job_id, created_at desc);

create table org.public_bodies (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  supersedes_id uuid references org.public_bodies(id),
  version integer not null default 1 check (version > 0),
  ibge_code text check (ibge_code is null or ibge_code ~ '^[0-9]{7}$'),
  official_code text,
  name text not null,
  body_type text not null check (
    body_type in ('executive', 'legislative', 'indirect_administration', 'oversight', 'other')
  ),
  jurisdiction text not null default 'municipal',
  state_code text check (state_code is null or state_code ~ '^[A-Z]{2}$'),
  active_from date,
  active_until date,
  created_at timestamptz not null default statement_timestamp(),
  check (active_until is null or active_from is null or active_until >= active_from)
);

create unique index public_bodies_ibge_active_idx
  on org.public_bodies (ibge_code, body_type)
  where ibge_code is not null and active_until is null;

create table org.departments (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  parent_department_id uuid references org.departments(id),
  supersedes_id uuid references org.departments(id),
  version integer not null default 1 check (version > 0),
  official_code text,
  name text not null,
  normalized_name text not null,
  valid_from date,
  valid_until date,
  created_at timestamptz not null default statement_timestamp(),
  check (valid_until is null or valid_from is null or valid_until >= valid_from)
);

create index departments_body_name_idx
  on org.departments (public_body_id, normalized_name);

create table hr.people (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  supersedes_id uuid references hr.people(id),
  version integer not null default 1 check (version > 0),
  display_name text not null,
  normalized_name text not null,
  identity_fingerprint text,
  birth_year smallint check (
    birth_year is null or birth_year between 1900 and extract(year from current_date)::integer
  ),
  created_at timestamptz not null default statement_timestamp()
);

comment on column hr.people.identity_fingerprint is
  'Pseudonymous deduplication key; never store a full CPF in this column.';

create index people_normalized_name_trgm_idx
  on hr.people using gin (normalized_name gin_trgm_ops);

create table hr.public_positions (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  supersedes_id uuid references hr.public_positions(id),
  version integer not null default 1 check (version > 0),
  official_code text,
  name text not null,
  normalized_name text not null,
  position_type text check (
    position_type is null or position_type in ('effective', 'commissioned', 'temporary', 'political', 'other')
  ),
  valid_from date,
  valid_until date,
  created_at timestamptz not null default statement_timestamp(),
  check (valid_until is null or valid_from is null or valid_until >= valid_from)
);

create index public_positions_name_trgm_idx
  on hr.public_positions using gin (normalized_name gin_trgm_ops);

create table hr.appointments (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  extraction_result_id uuid references raw.extraction_results(id),
  person_id uuid not null references hr.people(id),
  public_position_id uuid not null references hr.public_positions(id),
  department_id uuid references org.departments(id),
  supersedes_id uuid references hr.appointments(id),
  version integer not null default 1 check (version > 0),
  act_number text,
  act_date date not null,
  effective_from date,
  effective_until date,
  publication_state text not null default 'pending_review' check (
    publication_state in ('pending_review', 'approved', 'rejected', 'superseded', 'withdrawn')
  ),
  created_at timestamptz not null default statement_timestamp(),
  check (effective_until is null or effective_from is null or effective_until >= effective_from)
);

create index appointments_timeline_idx
  on hr.appointments (act_date desc, person_id);
create index appointments_filters_idx
  on hr.appointments (department_id, public_position_id, act_date desc);

create table hr.dismissals (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  extraction_result_id uuid references raw.extraction_results(id),
  person_id uuid not null references hr.people(id),
  public_position_id uuid references hr.public_positions(id),
  department_id uuid references org.departments(id),
  appointment_id uuid references hr.appointments(id),
  supersedes_id uuid references hr.dismissals(id),
  version integer not null default 1 check (version > 0),
  act_number text,
  act_date date not null,
  effective_date date,
  publication_state text not null default 'pending_review' check (
    publication_state in ('pending_review', 'approved', 'rejected', 'superseded', 'withdrawn')
  ),
  created_at timestamptz not null default statement_timestamp()
);

create index dismissals_timeline_idx
  on hr.dismissals (act_date desc, person_id);

create table hr.public_exams (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  supersedes_id uuid references hr.public_exams(id),
  version integer not null default 1 check (version > 0),
  title text not null,
  organizer text,
  exam_year smallint,
  status text not null check (
    status in ('announced', 'open', 'in_progress', 'homologated', 'expired', 'suspended', 'cancelled')
  ),
  validity_start date,
  validity_end date,
  created_at timestamptz not null default statement_timestamp(),
  check (validity_end is null or validity_start is null or validity_end >= validity_start)
);

create table hr.exam_notices (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_exam_id uuid not null references hr.public_exams(id),
  supersedes_id uuid references hr.exam_notices(id),
  version integer not null default 1 check (version > 0),
  notice_type text not null,
  notice_number text,
  publication_date date not null,
  summary text,
  created_at timestamptz not null default statement_timestamp()
);

create table hr.exam_calls (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_exam_id uuid not null references hr.public_exams(id),
  exam_notice_id uuid references hr.exam_notices(id),
  person_id uuid references hr.people(id),
  public_position_id uuid references hr.public_positions(id),
  supersedes_id uuid references hr.exam_calls(id),
  version integer not null default 1 check (version > 0),
  call_date date not null,
  classification integer check (classification is null or classification > 0),
  status text not null check (
    status in ('called', 'presented', 'appointed', 'waived', 'not_presented', 'cancelled', 'unknown')
  ),
  created_at timestamptz not null default statement_timestamp()
);

create table hr.payroll_entries (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  person_id uuid not null references hr.people(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  public_position_id uuid references hr.public_positions(id),
  supersedes_id uuid references hr.payroll_entries(id),
  version integer not null default 1 check (version > 0),
  reference_month date not null check (reference_month = date_trunc('month', reference_month)::date),
  gross_amount numeric(20,2) check (gross_amount is null or gross_amount >= 0),
  net_amount numeric(20,2) check (net_amount is null or net_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  publication_state text not null default 'restricted' check (
    publication_state in ('restricted', 'aggregate_only', 'approved', 'withheld')
  ),
  created_at timestamptz not null default statement_timestamp()
);

create index payroll_entries_reference_idx
  on hr.payroll_entries (reference_month desc, public_body_id);

create table hr.payroll_components (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  payroll_entry_id uuid not null references hr.payroll_entries(id),
  supersedes_id uuid references hr.payroll_components(id),
  version integer not null default 1 check (version > 0),
  component_code text,
  component_name text not null,
  component_type text not null check (
    component_type in ('earning', 'deduction', 'employer_charge', 'informational')
  ),
  amount numeric(20,2) not null,
  disclosure_class text not null default 'restricted' check (
    disclosure_class in ('public', 'aggregate_only', 'restricted', 'withheld')
  ),
  created_at timestamptz not null default statement_timestamp()
);

create table procurement.suppliers (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  supersedes_id uuid references procurement.suppliers(id),
  version integer not null default 1 check (version > 0),
  entity_type text not null check (entity_type in ('legal_entity', 'natural_person', 'foreign_entity', 'unknown')),
  legal_name text not null,
  normalized_name text not null,
  public_registration_type text check (
    public_registration_type is null or public_registration_type in ('CNPJ', 'FOREIGN', 'OTHER')
  ),
  public_registration_number text,
  private_identity_fingerprint text,
  municipality text,
  state_code text check (state_code is null or state_code ~ '^[A-Z]{2}$'),
  created_at timestamptz not null default statement_timestamp(),
  check (
    entity_type <> 'natural_person'
    or public_registration_number is null
  )
);

comment on column procurement.suppliers.private_identity_fingerprint is
  'Restricted pseudonymous key. Full CPF publication and storage are forbidden.';

create index suppliers_name_trgm_idx
  on procurement.suppliers using gin (normalized_name gin_trgm_ops);

create table procurement.supplier_relationships (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  supplier_id uuid not null references procurement.suppliers(id),
  related_supplier_id uuid references procurement.suppliers(id),
  related_person_id uuid references hr.people(id),
  supersedes_id uuid references procurement.supplier_relationships(id),
  version integer not null default 1 check (version > 0),
  relationship_type text not null,
  valid_from date,
  valid_until date,
  verification_state text not null default 'unverified' check (
    verification_state in ('unverified', 'source_confirmed', 'reviewed', 'rejected')
  ),
  created_at timestamptz not null default statement_timestamp(),
  check (num_nonnulls(related_supplier_id, related_person_id) = 1),
  check (valid_until is null or valid_from is null or valid_until >= valid_from)
);

create table procurement.procurements (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  supersedes_id uuid references procurement.procurements(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  process_number text,
  procurement_mode text,
  object_description text not null,
  legal_basis text,
  status text,
  publication_date date,
  opening_date timestamptz,
  estimated_amount numeric(20,2) check (estimated_amount is null or estimated_amount >= 0),
  awarded_amount numeric(20,2) check (awarded_amount is null or awarded_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  created_at timestamptz not null default statement_timestamp()
);

create unique index procurements_external_id_idx
  on procurement.procurements (public_body_id, external_id, version)
  where external_id is not null;
create index procurements_date_idx
  on procurement.procurements (publication_date desc, public_body_id);

create table procurement.procurement_items (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  procurement_id uuid not null references procurement.procurements(id),
  supersedes_id uuid references procurement.procurement_items(id),
  version integer not null default 1 check (version > 0),
  external_item_number text,
  description text not null,
  normalized_description text,
  catalog_code text,
  quantity numeric(24,6) check (quantity is null or quantity >= 0),
  unit_name text,
  estimated_unit_amount numeric(20,4) check (
    estimated_unit_amount is null or estimated_unit_amount >= 0
  ),
  estimated_total_amount numeric(20,2) check (
    estimated_total_amount is null or estimated_total_amount >= 0
  ),
  result_status text,
  created_at timestamptz not null default statement_timestamp()
);

create table procurement.bids (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  procurement_id uuid not null references procurement.procurements(id),
  procurement_item_id uuid references procurement.procurement_items(id),
  supplier_id uuid not null references procurement.suppliers(id),
  supersedes_id uuid references procurement.bids(id),
  version integer not null default 1 check (version > 0),
  bid_amount numeric(20,4) not null check (bid_amount >= 0),
  quantity numeric(24,6) check (quantity is null or quantity >= 0),
  result text check (
    result is null or result in ('submitted', 'classified', 'disqualified', 'winner', 'cancelled', 'unknown')
  ),
  result_date date,
  created_at timestamptz not null default statement_timestamp()
);

create index bids_supplier_idx
  on procurement.bids (supplier_id, result_date desc);

create table procurement.contracts (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  procurement_id uuid references procurement.procurements(id),
  supplier_id uuid references procurement.suppliers(id),
  supersedes_id uuid references procurement.contracts(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  contract_number text,
  object_description text not null,
  signed_date date,
  effective_from date,
  effective_until date,
  initial_amount numeric(20,2) check (initial_amount is null or initial_amount >= 0),
  current_amount numeric(20,2) check (current_amount is null or current_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  status text,
  created_at timestamptz not null default statement_timestamp(),
  check (effective_until is null or effective_from is null or effective_until >= effective_from)
);

create index contracts_supplier_date_idx
  on procurement.contracts (supplier_id, signed_date desc);

create table procurement.contract_amendments (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  contract_id uuid not null references procurement.contracts(id),
  supersedes_id uuid references procurement.contract_amendments(id),
  version integer not null default 1 check (version > 0),
  amendment_number text,
  amendment_type text,
  signed_date date,
  value_change numeric(20,2),
  duration_change_days integer,
  justification text,
  created_at timestamptz not null default statement_timestamp()
);

create table finance.commitments (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  supplier_id uuid references procurement.suppliers(id),
  procurement_id uuid references procurement.procurements(id),
  contract_id uuid references procurement.contracts(id),
  supersedes_id uuid references finance.commitments(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  commitment_number text,
  fiscal_year smallint not null,
  issue_date date,
  description text,
  amount numeric(20,2) not null check (amount >= 0),
  cancelled_amount numeric(20,2) not null default 0 check (cancelled_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  created_at timestamptz not null default statement_timestamp()
);

create index commitments_supplier_date_idx
  on finance.commitments (supplier_id, issue_date desc);

create table finance.liquidations (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  commitment_id uuid not null references finance.commitments(id),
  supersedes_id uuid references finance.liquidations(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  liquidation_number text,
  liquidation_date date not null,
  amount numeric(20,2) not null check (amount >= 0),
  cancelled_amount numeric(20,2) not null default 0 check (cancelled_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  created_at timestamptz not null default statement_timestamp()
);

create table finance.payments (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  commitment_id uuid references finance.commitments(id),
  liquidation_id uuid references finance.liquidations(id),
  supplier_id uuid references procurement.suppliers(id),
  supersedes_id uuid references finance.payments(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  payment_order_number text,
  payment_date date not null,
  amount numeric(20,2) not null check (amount >= 0),
  reversed_amount numeric(20,2) not null default 0 check (reversed_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  created_at timestamptz not null default statement_timestamp()
);

create index payments_supplier_date_idx
  on finance.payments (supplier_id, payment_date desc);

create table finance.revenues (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  supersedes_id uuid references finance.revenues(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  fiscal_year smallint not null,
  revenue_date date,
  revenue_code text,
  description text not null,
  forecast_amount numeric(20,2) check (forecast_amount is null or forecast_amount >= 0),
  collected_amount numeric(20,2) not null check (collected_amount >= 0),
  currency char(3) not null default 'BRL' check (currency = 'BRL'),
  created_at timestamptz not null default statement_timestamp()
);

create index revenues_year_code_idx
  on finance.revenues (fiscal_year desc, revenue_code);

create table procurement.public_works (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  public_body_id uuid not null references org.public_bodies(id),
  department_id uuid references org.departments(id),
  procurement_id uuid references procurement.procurements(id),
  contract_id uuid references procurement.contracts(id),
  supplier_id uuid references procurement.suppliers(id),
  supersedes_id uuid references procurement.public_works(id),
  version integer not null default 1 check (version > 0),
  external_id text,
  name text not null,
  description text,
  address_public text,
  latitude numeric(9,6) check (latitude is null or latitude between -90 and 90),
  longitude numeric(9,6) check (longitude is null or longitude between -180 and 180),
  planned_start date,
  planned_end date,
  actual_start date,
  actual_end date,
  physical_progress_percent numeric(6,3) check (
    physical_progress_percent is null
    or physical_progress_percent between 0 and 100
  ),
  initial_amount numeric(20,2) check (initial_amount is null or initial_amount >= 0),
  current_amount numeric(20,2) check (current_amount is null or current_amount >= 0),
  status text,
  created_at timestamptz not null default statement_timestamp()
);

create table analysis.anomaly_rules (
  id uuid primary key default gen_random_uuid(),
  slug text not null,
  version integer not null check (version > 0),
  name text not null,
  description text not null,
  deterministic_spec jsonb not null check (jsonb_typeof(deterministic_spec) = 'object'),
  implementation_version text not null,
  severity text not null check (severity in ('information', 'low', 'medium', 'high')),
  enabled boolean not null default false,
  methodology_url text,
  created_at timestamptz not null default statement_timestamp(),
  unique (slug, version)
);

create table analysis.anomaly_findings (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  anomaly_rule_id uuid not null references analysis.anomaly_rules(id),
  target_type text not null,
  target_id uuid not null,
  supersedes_id uuid references analysis.anomaly_findings(id),
  version integer not null default 1 check (version > 0),
  deterministic_inputs jsonb not null check (jsonb_typeof(deterministic_inputs) = 'object'),
  deterministic_output jsonb not null check (jsonb_typeof(deterministic_output) = 'object'),
  status text not null default 'triage' check (
    status in ('triage', 'needs_context', 'dismissed', 'confirmed_as_signal', 'superseded')
  ),
  public_explanation text,
  created_at timestamptz not null default statement_timestamp()
);

comment on table analysis.anomaly_findings is
  'A finding is a reviewable signal, never proof of illegality or corruption.';

create index anomaly_findings_target_idx
  on analysis.anomaly_findings (target_type, target_id, created_at desc);

create table evidence.evidence_items (
  id uuid primary key default gen_random_uuid(),
  target_type text not null,
  target_id uuid not null,
  raw_artifact_id uuid references raw.raw_artifacts(id),
  raw_record_id uuid references raw.raw_records(id),
  document_page_id uuid references raw.document_pages(id),
  extraction_result_id uuid references raw.extraction_results(id),
  evidence_kind text not null check (
    evidence_kind in ('source_record', 'document', 'page', 'excerpt', 'calculation', 'methodology')
  ),
  source_url text check (source_url is null or source_url ~ '^https://'),
  excerpt text,
  locator jsonb,
  content_sha256 text check (content_sha256 is null or content_sha256 ~ '^[0-9a-f]{64}$'),
  parser_version text not null,
  is_primary boolean not null default false,
  created_at timestamptz not null default statement_timestamp(),
  check (
    num_nonnulls(raw_artifact_id, raw_record_id, document_page_id, extraction_result_id) >= 1
  )
);

create index evidence_items_target_idx
  on evidence.evidence_items (target_type, target_id, is_primary desc);

create table evidence.source_conflicts (
  id uuid primary key default gen_random_uuid(),
  target_type text not null,
  target_id uuid not null,
  field_name text not null,
  first_evidence_item_id uuid not null references evidence.evidence_items(id),
  second_evidence_item_id uuid not null references evidence.evidence_items(id),
  first_value jsonb,
  second_value jsonb,
  status text not null default 'open' check (
    status in ('open', 'resolved', 'accepted_difference', 'superseded')
  ),
  resolution text,
  resolved_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  check (first_evidence_item_id <> second_evidence_item_id)
);

create table editorial.editorial_reviews (
  id uuid primary key default gen_random_uuid(),
  target_type text not null,
  target_id uuid not null,
  reviewer_subject text not null,
  review_type text not null check (
    review_type in ('data_quality', 'editorial', 'legal', 'privacy', 'security')
  ),
  decision text not null check (
    decision in ('approved', 'changes_requested', 'rejected', 'withdrawn')
  ),
  rationale text not null,
  checklist jsonb not null default '{}'::jsonb check (jsonb_typeof(checklist) = 'object'),
  reviewed_at timestamptz not null default statement_timestamp(),
  created_at timestamptz not null default statement_timestamp()
);

create index editorial_reviews_target_idx
  on editorial.editorial_reviews (target_type, target_id, reviewed_at desc);

create table editorial.published_insights (
  id uuid primary key default gen_random_uuid(),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  approved_review_id uuid not null references editorial.editorial_reviews(id),
  supersedes_id uuid references editorial.published_insights(id),
  version integer not null default 1 check (version > 0),
  slug text not null,
  title text not null,
  summary text not null,
  body jsonb not null,
  statement_class text not null check (
    statement_class in ('fact', 'inference', 'anomaly', 'hypothesis', 'methodology')
  ),
  status text not null default 'draft' check (
    status in ('draft', 'scheduled', 'published', 'corrected', 'withdrawn', 'superseded')
  ),
  published_at timestamptz,
  correction_notice text,
  created_at timestamptz not null default statement_timestamp(),
  unique (slug, version),
  check (status <> 'published' or published_at is not null)
);

create table editorial.citizen_alerts (
  id uuid primary key default gen_random_uuid(),
  owner_subject uuid,
  channel text not null check (channel in ('web', 'email', 'rss', 'web_push')),
  destination_ciphertext bytea,
  destination_hash text,
  filter_spec jsonb not null check (jsonb_typeof(filter_spec) = 'object'),
  consent_recorded_at timestamptz,
  unsubscribe_token_hash text,
  status text not null default 'active' check (
    status in ('active', 'paused', 'unsubscribed', 'bounced', 'deleted')
  ),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (
    channel in ('web', 'rss')
    or (
      destination_ciphertext is not null
      and destination_hash is not null
      and consent_recorded_at is not null
      and unsubscribe_token_hash is not null
    )
  )
);

create trigger citizen_alerts_set_updated_at
before update on editorial.citizen_alerts
for each row execute function audit.set_updated_at();

create table audit.audit_events (
  id bigint generated always as identity primary key,
  event_id uuid not null default gen_random_uuid() unique,
  occurred_at timestamptz not null default statement_timestamp(),
  actor_type text not null check (
    actor_type in ('system', 'worker', 'administrator', 'reviewer', 'citizen')
  ),
  actor_subject text,
  action text not null,
  target_type text not null,
  target_id text,
  request_id text,
  ip_hash text,
  before_state jsonb,
  after_state jsonb,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object')
);

create index audit_events_target_idx
  on audit.audit_events (target_type, target_id, occurred_at desc);
create index audit_events_request_idx
  on audit.audit_events (request_id)
  where request_id is not null;

do $$
declare
  relation_name text;
begin
  foreach relation_name in array array[
    'raw.raw_artifacts',
    'raw.raw_records',
    'raw.document_pages',
    'raw.extraction_results',
    'audit.audit_events'
  ]
  loop
    execute format(
      'create trigger reject_mutation before update or delete on %s for each row execute function audit.reject_mutation()',
      relation_name
    );
  end loop;
end
$$;

comment on schema api is
  'Only reviewed, minimized public projections may be exposed through the Supabase Data API.';
comment on schema raw is
  'Immutable source evidence. Corrections are appended as new artifacts, records or extraction results.';
comment on schema editorial is
  'Human review and publication workflow; no reputational conclusion may bypass review.';

commit;
