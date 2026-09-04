begin;

create index if not exists raw_artifacts_tcm_ba_monthly_pdf_idx
on raw.raw_artifacts (id) include (sha256)
where artifact_kind = 'document'
  and metadata ->> 'schema_name' = 'tcm-ba-monthly-document'
  and content_type = 'application/pdf'
  and http_status between 200 and 299;

create index if not exists document_pages_tcm_ba_embedded_text_idx
on raw.document_pages (raw_artifact_id, page_number)
include (text_sha256)
where parser_version = 'gazette-pdf-embedded-text/1.1.0';

create index if not exists document_pages_tcm_ba_ocr_text_idx
on raw.document_pages (raw_artifact_id, page_number, created_at desc)
include (text_sha256)
where parser_version = 'tcm-ba-document-ocr-text/1.0.0'
  and text_content is not null;

create index if not exists extraction_jobs_tcm_ba_commitment_current_idx
on raw.extraction_jobs (raw_artifact_id, idempotency_key)
include (id, status)
where job_type = 'tcm_ba_commitment_candidates';

analyze raw.raw_artifacts;
analyze raw.document_pages;
analyze raw.extraction_jobs;

commit;
