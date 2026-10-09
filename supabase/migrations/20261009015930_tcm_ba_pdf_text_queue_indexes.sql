begin;

-- A fila de PDFs mensais do TCM-BA sem texto (pending_tcm_ba_pdf_artifacts)
-- sondava, para cada um dos 20 mil PDFs, o índice largo de páginas (600 mil
-- entradas com hash) e lia as linhas largas de raw_artifacts: 9,4 s fora de
-- pico e acima dos 15 s do coletor sob a carga do OCR (cancelada a cada
-- 15 min em 09/10/2026). Páginas de um PDF são gravadas numa transação e
-- numeradas a partir de 1 (conferido: 19.126 de 19.126 artefatos com página
-- 1), então "tem página desta versão" equivale a "tem a página 1": índice
-- de uma entrada por PDF. A fila ordenada passa a ser lida só do índice.
-- 9,4 s -> 0,96 s com cache frio.
create index if not exists document_pages_embedded_first_page_idx
  on raw.document_pages (raw_artifact_id)
  where parser_version = 'gazette-pdf-embedded-text/1.1.0'
    and page_number = 1;

create index if not exists raw_artifacts_tcm_ba_pdf_queue_idx
  on raw.raw_artifacts (created_at, id) include (sha256, object_key)
  where artifact_kind = 'document'
    and (metadata ->> 'schema_name') = 'tcm-ba-monthly-document'
    and object_key like 'tcm-ba/monthly-documents/%/pdf/%'
    and content_type = 'application/pdf'
    and http_status between 200 and 299;

commit;
