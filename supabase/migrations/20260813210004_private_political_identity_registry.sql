begin;

create table private.person_identifier_sources (
  id uuid primary key default gen_random_uuid(),
  source_name text not null check (
    source_name in ('tse_candidate_registry', 'official_appointment_record')
  ),
  source_record_key text not null check (length(btrim(source_record_key)) > 0),
  election_year integer check (election_year is null or election_year between 1994 and 2100),
  source_url text not null check (source_url ~ '^https://'),
  encrypted_payload bytea not null check (octet_length(encrypted_payload) > 0),
  nonce bytea not null check (octet_length(nonce) = 12),
  authentication_tag bytea not null check (octet_length(authentication_tag) = 16),
  payload_sha256 char(64) not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  archive_sha256 char(64) check (
    archive_sha256 is null or archive_sha256 ~ '^[0-9a-f]{64}$'
  ),
  state_file_sha256 char(64) check (
    state_file_sha256 is null or state_file_sha256 ~ '^[0-9a-f]{64}$'
  ),
  key_version smallint not null check (key_version > 0),
  parser_version text not null check (length(btrim(parser_version)) > 0),
  collected_at timestamptz not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (source_name, source_record_key, payload_sha256)
);

comment on table private.person_identifier_sources is
  'Cópia cifrada da linha oficial que sustentou um identificador privado; conteúdo nunca exposto pelo Data API.';

alter table private.person_identifiers
  add column source_evidence_id uuid
    references private.person_identifier_sources(id),
  add column verification_status text not null default 'verified' check (
    verification_status in ('verified', 'conflicted', 'superseded')
  ),
  add column verified_at timestamptz not null default statement_timestamp();

alter table private.person_identifiers
  alter column source_evidence_id set not null;

create unique index person_identifiers_source_evidence_unique_idx
  on private.person_identifiers (source_evidence_id)
  where source_evidence_id is not null;

create table identity.person_source_links (
  id uuid primary key default gen_random_uuid(),
  person_id uuid not null references hr.people(id),
  source_kind text not null check (
    source_kind in (
      'tse_candidate',
      'municipal_executive',
      'municipal_councillor',
      'federal_deputy',
      'state_deputy'
    )
  ),
  source_external_id text not null check (length(btrim(source_external_id)) > 0),
  election_year integer check (election_year is null or election_year between 1994 and 2100),
  office text,
  link_method text not null check (
    link_method in ('cpf_exact', 'official_identifier', 'human_review')
  ),
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_evidence_id uuid references private.person_identifier_sources(id),
  review_status text not null default 'approved' check (
    review_status in ('pending', 'approved', 'rejected', 'conflicted')
  ),
  created_at timestamptz not null default statement_timestamp(),
  check (link_method <> 'cpf_exact' or source_evidence_id is not null)
);

create unique index person_source_links_identity_unique_idx
  on identity.person_source_links (
    source_kind,
    source_external_id,
    coalesce(election_year, 0),
    coalesce(office, '')
  );
create index person_source_links_person_idx
  on identity.person_source_links (person_id, source_kind, election_year);

comment on table identity.person_source_links is
  'Vínculos internos entre uma pessoa canônica e identificadores oficiais de cada fonte e período.';

create table private.person_identifier_conflicts (
  id uuid primary key default gen_random_uuid(),
  identifier_type text not null check (identifier_type = 'cpf'),
  fingerprint char(64) not null check (fingerprint ~ '^[0-9a-f]{64}$'),
  existing_person_id uuid not null references hr.people(id),
  incoming_source_kind text not null,
  incoming_source_external_id text not null,
  source_evidence_id uuid not null references private.person_identifier_sources(id),
  reason text not null check (
    reason in ('fingerprint_linked_to_other_person', 'person_has_other_fingerprint')
  ),
  status text not null default 'open' check (
    status in ('open', 'resolved', 'accepted_difference', 'superseded')
  ),
  resolution text,
  resolved_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  unique (source_evidence_id, reason),
  check (status = 'open' or resolved_at is not null)
);

comment on table private.person_identifier_conflicts is
  'Conflitos de identidade sem CPF em claro; impedem fusão automática de pessoas incompatíveis.';

alter table private.person_identifier_sources enable row level security;
alter table private.person_identifier_sources force row level security;
alter table private.person_identifier_conflicts enable row level security;
alter table private.person_identifier_conflicts force row level security;
alter table identity.person_source_links enable row level security;
alter table identity.person_source_links force row level security;
alter table hr.people enable row level security;
alter table hr.people force row level security;

revoke all on table private.person_identifier_sources,
  private.person_identifier_conflicts,
  identity.person_source_links,
  hr.people
from public, anon, authenticated, collector_worker;

grant usage on schema hr, raw, political to identity_worker;
grant select, insert on table hr.people to identity_worker;
grant select on table raw.raw_records to identity_worker;
grant select on table political.representative_tse_crosswalk to identity_worker;
grant select, insert on table private.person_identifier_sources,
  private.person_identifier_conflicts,
  identity.person_source_links
to identity_worker;

create policy identity_worker_people_select
on hr.people for select to identity_worker using (true);
create policy identity_worker_people_insert
on hr.people for insert to identity_worker with check (true);
create policy identity_worker_raw_records_select
on raw.raw_records for select to identity_worker using (true);
create policy identity_worker_crosswalk_select
on political.representative_tse_crosswalk
for select to identity_worker using (review_status = 'approved');
create policy identity_worker_identifier_sources_select
on private.person_identifier_sources
for select to identity_worker using (true);
create policy identity_worker_identifier_sources_insert
on private.person_identifier_sources
for insert to identity_worker with check (true);
create policy identity_worker_identifier_conflicts_select
on private.person_identifier_conflicts
for select to identity_worker using (true);
create policy identity_worker_identifier_conflicts_insert
on private.person_identifier_conflicts
for insert to identity_worker with check (status = 'open');
create policy identity_worker_person_source_links_select
on identity.person_source_links
for select to identity_worker using (true);
create policy identity_worker_person_source_links_insert
on identity.person_source_links
for insert to identity_worker
with check (
  review_status in ('pending', 'approved', 'conflicted')
  and (link_method <> 'cpf_exact' or review_status = 'approved')
);

commit;
