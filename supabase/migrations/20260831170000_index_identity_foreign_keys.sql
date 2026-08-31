begin;

-- Estes indices cobrem exclusivamente as FKs de linhagem e evidencia usadas
-- pelo registro privado de identidade. Nao indexamos CPF cifrado, fingerprint
-- ou os quatro ultimos digitos neste lote.

create index person_aliases_origin_artifact_idx
  on identity.person_aliases (origin_raw_artifact_id);

create index person_aliases_origin_record_idx
  on identity.person_aliases (origin_raw_record_id);

create index person_source_links_origin_record_idx
  on identity.person_source_links (origin_raw_record_id);

create index person_source_links_source_evidence_idx
  on identity.person_source_links (source_evidence_id);

create index person_identifier_conflicts_existing_person_idx
  on private.person_identifier_conflicts (existing_person_id);

create index person_identifier_gaps_origin_record_idx
  on private.person_identifier_gaps (origin_raw_record_id);

create index person_identifiers_origin_artifact_idx
  on private.person_identifiers (origin_raw_artifact_id);

create index person_identifiers_origin_record_idx
  on private.person_identifiers (origin_raw_record_id);

commit;
