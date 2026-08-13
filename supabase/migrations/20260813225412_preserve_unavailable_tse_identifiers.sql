begin;

create table private.person_identifier_gaps (
  id uuid primary key default gen_random_uuid(),
  identifier_type text not null check (identifier_type = 'cpf'),
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
  election_year integer not null check (election_year between 1994 and 2100),
  office text,
  origin_raw_record_id uuid not null references raw.raw_records(id),
  source_evidence_id uuid not null references private.person_identifier_sources(id),
  reason text not null check (
    reason in ('missing_official_value', 'invalid_official_value')
  ),
  status text not null default 'open' check (
    status in ('open', 'resolved', 'superseded')
  ),
  resolved_at timestamptz,
  created_at timestamptz not null default statement_timestamp(),
  unique (source_evidence_id, reason),
  check (status = 'open' or resolved_at is not null)
);

comment on table private.person_identifier_gaps is
  'Linhas oficiais cifradas cujo CPF está ausente ou inválido; não cria identidade nem fica exposta pelo Data API.';

comment on table private.person_identifier_sources is
  'Cópia cifrada da linha oficial usada para identidade ou para comprovar identificador indisponível; nunca exposta pelo Data API.';

alter table private.person_identifier_gaps enable row level security;
alter table private.person_identifier_gaps force row level security;

revoke all on table private.person_identifier_gaps
from public, anon, authenticated, collector_worker;
grant select, insert on table private.person_identifier_gaps to identity_worker;

create policy identity_worker_identifier_gaps_select
on private.person_identifier_gaps
for select to identity_worker using (true);
create policy identity_worker_identifier_gaps_insert
on private.person_identifier_gaps
for insert to identity_worker with check (status = 'open');

create function identity.register_tse_identifier_gap(
  p_source_record_key text,
  p_election_year integer,
  p_source_url text,
  p_encrypted_payload bytea,
  p_payload_nonce bytea,
  p_payload_tag bytea,
  p_payload_sha256 text,
  p_archive_sha256 text,
  p_state_file_sha256 text,
  p_key_version integer,
  p_parser_version text,
  p_collected_at timestamptz,
  p_source_kind text,
  p_source_external_id text,
  p_office text,
  p_origin_raw_record_id uuid,
  p_reason text
)
returns table (
  status text,
  gap_id uuid,
  source_evidence_id uuid
)
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  evidence_id uuid;
  persisted_gap_id uuid;
  raw_artifact_id uuid;
  canonical_source_kind text;
  inserted_gap boolean := false;
begin
  if p_source_kind not in ('municipal', 'executive', 'federal', 'state') then
    raise exception 'source_kind privado inválido' using errcode = '22023';
  end if;
  if p_reason not in ('missing_official_value', 'invalid_official_value') then
    raise exception 'motivo de lacuna privada inválido' using errcode = '22023';
  end if;
  if p_source_url !~ '^https://' then
    raise exception 'source_url privada deve usar HTTPS' using errcode = '22023';
  end if;

  canonical_source_kind := case p_source_kind
    when 'municipal' then 'municipal_councillor'
    when 'executive' then 'municipal_executive'
    when 'federal' then 'federal_deputy'
    when 'state' then 'state_deputy'
  end;

  select record.raw_artifact_id
  into raw_artifact_id
  from raw.raw_records as record
  where record.id = p_origin_raw_record_id;
  if raw_artifact_id is null then
    raise exception 'registro bruto de origem inexistente' using errcode = '23503';
  end if;

  insert into private.person_identifier_sources (
    source_name, source_record_key, election_year, source_url,
    encrypted_payload, nonce, authentication_tag, payload_sha256,
    archive_sha256, state_file_sha256, key_version, parser_version,
    collected_at
  ) values (
    'tse_candidate_registry', p_source_record_key, p_election_year,
    p_source_url, p_encrypted_payload, p_payload_nonce, p_payload_tag,
    p_payload_sha256, p_archive_sha256, p_state_file_sha256,
    p_key_version, p_parser_version, p_collected_at
  ) on conflict (source_name, source_record_key, payload_sha256) do nothing;

  select source.id
  into evidence_id
  from private.person_identifier_sources as source
  where source.source_name = 'tse_candidate_registry'
    and source.source_record_key = p_source_record_key
    and source.payload_sha256 = p_payload_sha256;

  insert into private.person_identifier_gaps (
    identifier_type, source_kind, source_external_id, election_year,
    office, origin_raw_record_id, source_evidence_id, reason
  ) values (
    'cpf', canonical_source_kind, p_source_external_id, p_election_year,
    p_office, p_origin_raw_record_id, evidence_id, p_reason
  ) on conflict on constraint person_identifier_gaps_source_evidence_id_reason_key
  do nothing
  returning id into persisted_gap_id;

  if persisted_gap_id is not null then
    inserted_gap := true;
  else
    select gap.id
    into persisted_gap_id
    from private.person_identifier_gaps as gap
    where gap.source_evidence_id = evidence_id
      and gap.reason = p_reason;
  end if;

  return query select
    case when inserted_gap then 'inserted' else 'unchanged' end,
    persisted_gap_id,
    evidence_id;
end;
$function$;

revoke all on function identity.register_tse_identifier_gap(
  text, integer, text, bytea, bytea, bytea, text, text, text, integer,
  text, timestamptz, text, text, text, uuid, text
) from public, anon, authenticated, collector_worker;
grant execute on function identity.register_tse_identifier_gap(
  text, integer, text, bytea, bytea, bytea, text, text, text, integer,
  text, timestamptz, text, text, text, uuid, text
) to identity_worker;

commit;
