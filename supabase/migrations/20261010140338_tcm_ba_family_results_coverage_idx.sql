begin;

-- Cobertura de famílias do TCM-BA lida só do índice: as 20 mil
-- classificações ficam espalhadas por 407 MB de extraction_results e, com
-- cache frio, a leitura do heap passava dos 15 s do coletor (10/10/2026).
-- Removido em 20261010140415: o planejador não usou leitura só do índice.
create index if not exists extraction_results_tcm_ba_family_coverage_idx
  on raw.extraction_results (
    extraction_job_id,
    validation_status,
    (result_payload ->> 'family'),
    (result_payload ->> 'schema_name')
  )
  where candidate_type = 'tcm_ba_document_family'
    and extractor_version = 'tcm-ba-document-family-inventory/1.3.0';

commit;
