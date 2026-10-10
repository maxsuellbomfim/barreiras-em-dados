begin;

-- Jobs atuais de segmentos e campos contratuais do TCM-BA por artefato e
-- chave, sem varrer os 47 mil jobs (mesmo padrão de famílias e empenhos).
create index if not exists extraction_jobs_tcm_ba_contract_segments_current_idx
  on raw.extraction_jobs (raw_artifact_id, idempotency_key)
  include (id, status)
  where job_type = 'tcm_ba_contract_document_segments';

create index if not exists extraction_jobs_tcm_ba_contract_fields_current_idx
  on raw.extraction_jobs (raw_artifact_id, idempotency_key)
  include (id, status)
  where job_type = 'tcm_ba_contract_field_candidates';

commit;
