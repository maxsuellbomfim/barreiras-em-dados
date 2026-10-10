begin;

-- PDFs do TCM-BA classificados como contratos e aditivos (545 em 10/10/2026):
-- a fila e a cobertura de segmentos contratuais liam o payload das 16 mil
-- classificações para achá-los (~4-5 s por consulta).
create index if not exists extraction_results_tcm_ba_contract_family_idx
  on raw.extraction_results (extraction_job_id)
  where candidate_type = 'tcm_ba_document_family'
    and extractor_version = 'tcm-ba-document-family-inventory/1.3.0'
    and validation_status = 'valid'
    and (result_payload ->> 'family') = 'contracts_and_amendments';

commit;
