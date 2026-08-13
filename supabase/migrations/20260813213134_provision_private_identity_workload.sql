begin;

-- A role de login nasce desativada. Senha e LOGIN pertencem ao procedimento
-- operacional e nunca entram em migration, workflow ou log.
do $migration$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'identity_registry'
  ) then
    create role identity_registry
      nologin
      inherit
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls
      connection limit 1;
  elsif exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'identity_registry'
      and (
        rolcanlogin
        or rolsuper
        or rolcreatedb
        or rolcreaterole
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception 'identity_registry exists with unsafe attributes';
  end if;
end
$migration$;

alter role identity_registry
  nologin
  inherit
  connection limit 1;
alter role identity_registry set statement_timeout = '15s';
alter role identity_registry set lock_timeout = '5s';
alter role identity_registry set idle_in_transaction_session_timeout = '15s';
alter role identity_registry
  set search_path = private, identity, hr, political, raw, pg_catalog;

grant identity_worker to identity_registry;

create function identity.register_tse_identity(
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
  p_encrypted_identifier bytea,
  p_identifier_nonce bytea,
  p_identifier_tag bytea,
  p_fingerprint text,
  p_last_four text,
  p_display_name text,
  p_normalized_name text,
  p_ballot_name text
)
returns table (
  status text,
  person_id uuid,
  source_evidence_id uuid
)
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  evidence_id uuid;
  linked_person_id uuid;
  fingerprint_person_id uuid;
  resolved_person_id uuid;
  raw_artifact_id uuid;
  existing_fingerprint text;
  inserted_identifier boolean := false;
  canonical_source_kind text;
begin
  if p_source_kind not in ('municipal', 'executive', 'federal', 'state') then
    raise exception 'source_kind privado inválido' using errcode = '22023';
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

  select link.person_id
  into linked_person_id
  from identity.person_source_links as link
  where link.source_kind = canonical_source_kind
    and link.source_external_id = p_source_external_id
    and coalesce(link.election_year, 0) = p_election_year
    and coalesce(link.office, '') = coalesce(p_office, '');

  select identifier.person_id
  into fingerprint_person_id
  from private.person_identifiers as identifier
  where identifier.identifier_type = 'cpf'
    and identifier.fingerprint = p_fingerprint;

  if linked_person_id is not null
     and fingerprint_person_id is not null
     and linked_person_id <> fingerprint_person_id then
    insert into private.person_identifier_conflicts (
      identifier_type, fingerprint, existing_person_id,
      incoming_source_kind, incoming_source_external_id,
      source_evidence_id, reason
    ) values (
      'cpf', p_fingerprint, linked_person_id, canonical_source_kind,
      p_source_external_id, evidence_id, 'fingerprint_linked_to_other_person'
    ) on conflict do nothing;
    return query select 'conflicted'::text, linked_person_id, evidence_id;
    return;
  end if;

  resolved_person_id := coalesce(linked_person_id, fingerprint_person_id);
  if resolved_person_id is not null then
    select identifier.fingerprint
    into existing_fingerprint
    from private.person_identifiers as identifier
    where identifier.person_id = resolved_person_id
      and identifier.identifier_type = 'cpf';
    if existing_fingerprint is not null
       and existing_fingerprint <> p_fingerprint then
      insert into private.person_identifier_conflicts (
        identifier_type, fingerprint, existing_person_id,
        incoming_source_kind, incoming_source_external_id,
        source_evidence_id, reason
      ) values (
        'cpf', p_fingerprint, resolved_person_id, canonical_source_kind,
        p_source_external_id, evidence_id, 'person_has_other_fingerprint'
      ) on conflict do nothing;
      return query select 'conflicted'::text, resolved_person_id, evidence_id;
      return;
    end if;
  end if;

  if resolved_person_id is null then
    insert into hr.people (
      origin_raw_record_id, display_name, normalized_name
    ) values (
      p_origin_raw_record_id, p_display_name, p_normalized_name
    ) returning id into resolved_person_id;
  end if;

  if not exists (
    select 1 from private.person_identifiers as identifier
    where identifier.person_id = resolved_person_id
      and identifier.identifier_type = 'cpf'
  ) then
    insert into private.person_identifiers (
      person_id, identifier_type, encrypted_value, nonce,
      authentication_tag, fingerprint, last_four, key_version, purpose,
      legal_basis, origin_raw_artifact_id, origin_raw_record_id,
      source_collected_at, source_evidence_id
    ) values (
      resolved_person_id, 'cpf', p_encrypted_identifier,
      p_identifier_nonce, p_identifier_tag, p_fingerprint, p_last_four,
      p_key_version, 'identity_resolution',
      'identificação e reconciliação de agentes públicos em fontes oficiais',
      raw_artifact_id, p_origin_raw_record_id, p_collected_at, evidence_id
    );
    inserted_identifier := true;
  end if;

  insert into identity.person_source_links (
    person_id, source_kind, source_external_id, election_year, office,
    link_method, origin_raw_record_id, source_evidence_id, review_status
  ) values (
    resolved_person_id, canonical_source_kind, p_source_external_id,
    p_election_year, p_office, 'cpf_exact', p_origin_raw_record_id,
    evidence_id, 'approved'
  ) on conflict (
    source_kind, source_external_id,
    coalesce(election_year, 0), coalesce(office, '')
  ) do nothing;

  insert into identity.person_aliases (
    person_id, alias, normalized_alias, alias_type, valid_from,
    origin_raw_record_id, review_status
  ) values (
    resolved_person_id, p_display_name, p_normalized_name, 'civil',
    make_date(p_election_year, 1, 1), p_origin_raw_record_id, 'approved'
  ) on conflict do nothing;

  if nullif(btrim(p_ballot_name), '') is not null then
    insert into identity.person_aliases (
      person_id, alias, normalized_alias, alias_type, valid_from,
      origin_raw_record_id, review_status
    ) values (
      resolved_person_id, p_ballot_name, lower(btrim(p_ballot_name)), 'ballot',
      make_date(p_election_year, 1, 1), p_origin_raw_record_id, 'approved'
    ) on conflict do nothing;
  end if;

  return query select
    case when inserted_identifier then 'inserted' else 'unchanged' end,
    resolved_person_id,
    evidence_id;
end;
$function$;

revoke all on function identity.register_tse_identity(
  text, integer, text, bytea, bytea, bytea, text, text, text, integer,
  text, timestamptz, text, text, text, uuid, bytea, bytea, bytea, text,
  text, text, text, text
) from public, anon, authenticated, collector_worker;
grant execute on function identity.register_tse_identity(
  text, integer, text, bytea, bytea, bytea, text, text, text, integer,
  text, timestamptz, text, text, text, uuid, bytea, bytea, bytea, text,
  text, text, text, text
) to identity_worker;

commit;
