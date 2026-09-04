begin;

create index if not exists raw_artifacts_bahia_state_execution_pending_idx
  on raw.raw_artifacts (retrieved_at desc, id desc)
  include (sha256, object_key, source_url)
  where artifact_kind = 'archive'
    and content_type in ('application/zip', 'application/octet-stream')
    and object_key like 'bahia/emendas-estaduais/archive/%';

create index if not exists raw_records_bahia_state_archive_member_idx
  on raw.raw_records (raw_artifact_id)
  where record_type = 'bahia_state_amendment_archive_member';

create index if not exists extraction_jobs_bahia_state_artifact_idx
  on raw.extraction_jobs (raw_artifact_id, status, id)
  where job_type = 'bahia_state_execution_aggregates_v1';

comment on index raw.raw_artifacts_bahia_state_execution_pending_idx is
  'Fila limitada aos ZIPs estaduais elegiveis, na mesma ordem do normalizador.';
comment on index raw.raw_records_bahia_state_archive_member_idx is
  'Comprova os cinco membros validados sem varrer todo o acervo bruto.';
comment on index raw.extraction_jobs_bahia_state_artifact_idx is
  'Resolve os estados processado e dead-letter por artefato estadual.';

commit;
