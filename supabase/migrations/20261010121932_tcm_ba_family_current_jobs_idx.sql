begin;

-- Cobertura de famílias do TCM-BA: jobs atuais por artefato e chave de
-- idempotência sem ler a linha do job (mesmo padrão dos empenhos). Com o
-- resultado estreito materializado na consulta, 4 s -> 0,37 s (10/10/2026).
create index if not exists extraction_jobs_tcm_ba_family_current_idx
  on raw.extraction_jobs (raw_artifact_id, idempotency_key)
  include (id, status)
  where job_type = 'tcm_ba_document_family_inventory';

commit;
