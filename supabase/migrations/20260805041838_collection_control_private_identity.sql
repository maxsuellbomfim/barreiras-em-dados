begin;

create schema if not exists private;
create schema if not exists identity;

create table source.collection_partitions (
  id uuid primary key default gen_random_uuid(),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  partition_key text not null check (length(btrim(partition_key)) between 3 and 200),
  period_start date not null,
  period_end date not null,
  status text not null check (
    status in ('complete', 'empty', 'partial', 'failed', 'blocked')
  ),
  expected_records integer check (expected_records is null or expected_records >= 0),
  observed_records integer not null default 0 check (observed_records >= 0),
  collection_run_id uuid references source.collection_runs(id),
  checkpoint jsonb not null default '{}'::jsonb
    check (jsonb_typeof(checkpoint) = 'object'),
  block_reason text,
  last_attempted_at timestamptz not null default statement_timestamp(),
  completed_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  unique (source_endpoint_id, partition_key),
  check (period_start <= period_end),
  check (status <> 'empty' or observed_records = 0),
  check (status not in ('complete', 'empty') or completed_at is not null),
  check (status <> 'blocked' or length(btrim(block_reason)) > 0)
);

create index collection_partitions_coverage_idx
  on source.collection_partitions (source_endpoint_id, period_start, period_end);
create index collection_partitions_attention_idx
  on source.collection_partitions (status, last_attempted_at desc)
  where status in ('partial', 'failed', 'blocked');
create index collection_partitions_run_idx
  on source.collection_partitions (collection_run_id);

create trigger collection_partitions_set_updated_at
before update on source.collection_partitions
for each row execute function audit.set_updated_at();

create table source.collection_failures (
  id uuid primary key default gen_random_uuid(),
  collection_run_id uuid not null unique references source.collection_runs(id),
  source_endpoint_id uuid not null references source.source_endpoints(id),
  partition_key text not null,
  status text not null check (
    status in ('open', 'retry_scheduled', 'dead_lettered', 'resolved')
  ),
  error_type text not null check (length(btrim(error_type)) between 1 and 120),
  error_detail text not null check (length(error_detail) between 1 and 500),
  attempt_count integer not null check (attempt_count >= 1),
  retryable boolean not null,
  next_retry_at timestamptz,
  failed_at timestamptz not null,
  dead_lettered_at timestamptz,
  resolved_at timestamptz,
  resolution_run_id uuid references source.collection_runs(id),
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  check (status <> 'retry_scheduled' or retryable),
  check (status <> 'dead_lettered' or dead_lettered_at is not null),
  check (status <> 'resolved' or resolved_at is not null)
);

create index collection_failures_attention_idx
  on source.collection_failures (status, failed_at desc)
  where status <> 'resolved';
create index collection_failures_endpoint_idx
  on source.collection_failures (source_endpoint_id, failed_at desc);
create index collection_failures_resolution_run_idx
  on source.collection_failures (resolution_run_id);

create trigger collection_failures_set_updated_at
before update on source.collection_failures
for each row execute function audit.set_updated_at();

create table private.person_identifiers (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references hr.people(id),
  identifier_type text not null check (identifier_type = 'cpf'),
  encrypted_value bytea not null check (octet_length(encrypted_value) > 0),
  nonce bytea not null check (octet_length(nonce) = 12),
  authentication_tag bytea not null check (octet_length(authentication_tag) = 16),
  fingerprint char(64) not null check (fingerprint ~ '^[0-9a-f]{64}$'),
  last_four char(4) not null check (last_four ~ '^[0-9]{4}$'),
  key_version smallint not null check (key_version > 0),
  purpose text not null check (
    purpose in ('identity_resolution', 'source_reconciliation')
  ),
  legal_basis text not null check (length(btrim(legal_basis)) > 0),
  origin_raw_artifact_id uuid references raw.raw_artifacts(id),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_collected_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (person_id, identifier_type),
  unique (identifier_type, fingerprint)
);

comment on table private.person_identifiers is
  'Identificadores pessoais cifrados para reconciliação interna; nunca expostos pelo Data API.';
comment on column private.person_identifiers.fingerprint is
  'HMAC-SHA-256 com chave separada; não é hash simples do CPF.';

create table identity.person_aliases (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references hr.people(id),
  alias text not null check (length(btrim(alias)) between 2 and 300),
  normalized_alias text not null check (
    length(btrim(normalized_alias)) between 2 and 300
  ),
  alias_type text not null check (
    alias_type in ('civil', 'ballot', 'historical', 'spelling', 'office')
  ),
  valid_from date,
  valid_until date,
  origin_raw_artifact_id uuid references raw.raw_artifacts(id),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  review_status text not null default 'pending' check (
    review_status in ('pending', 'approved', 'rejected')
  ),
  created_at timestamptz not null default statement_timestamp(),
  unique (person_id, normalized_alias, alias_type, valid_from),
  check (valid_until is null or valid_from is null or valid_until >= valid_from)
);

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'identity_worker'
  ) then
    create role identity_worker nologin nosuperuser nocreatedb
      nocreaterole noinherit noreplication;
  end if;
end
$$;

alter role identity_worker set statement_timeout = '15s';
alter role identity_worker set lock_timeout = '5s';

alter table source.collection_partitions enable row level security;
alter table source.collection_partitions force row level security;
alter table source.collection_failures enable row level security;
alter table source.collection_failures force row level security;
alter table private.person_identifiers enable row level security;
alter table private.person_identifiers force row level security;
alter table identity.person_aliases enable row level security;
alter table identity.person_aliases force row level security;

revoke all on schema private, identity from public, anon, authenticated;
revoke all on table source.collection_partitions, source.collection_failures
  from public, anon, authenticated;
revoke all on table private.person_identifiers, identity.person_aliases
  from public, anon, authenticated, collector_worker;

grant select, insert, update on source.collection_partitions to collector_worker;
grant select, insert, update on source.collection_failures to collector_worker;

create policy collector_worker_collection_partitions_all
on source.collection_partitions
for all to collector_worker
using (true)
with check (true);

create policy collector_worker_collection_failures_all
on source.collection_failures
for all to collector_worker
using (true)
with check (true);

grant usage on schema private, identity to identity_worker;
grant select, insert on private.person_identifiers to identity_worker;
grant select, insert on identity.person_aliases to identity_worker;

create policy identity_worker_person_identifiers_select
on private.person_identifiers
for select to identity_worker
using (true);

create policy identity_worker_person_identifiers_insert
on private.person_identifiers
for insert to identity_worker
with check (true);

create policy identity_worker_person_aliases_select
on identity.person_aliases
for select to identity_worker
using (true);

create policy identity_worker_person_aliases_insert
on identity.person_aliases
for insert to identity_worker
with check (true);

commit;
