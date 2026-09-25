begin;

-- A fila de edições integrais (GazetteDocumentRepository.pending_artifacts)
-- passou do statement_timeout de 15 s do coletor em 24/09 (execução #16 do
-- dreno de OCR). Sem carga levava 7,2 s: para saber numeração, páginas com
-- texto e horário da página mais nova lia ~36 mil páginas inteiras (com o
-- texto) e ordenava em disco. As duas agregações passam a ser respondidas só
-- pelos índices abaixo.
create index document_pages_artifact_page_created_idx
  on raw.document_pages (raw_artifact_id, page_number, created_at);

create index document_pages_text_pages_idx
  on raw.document_pages (raw_artifact_id, page_number)
  where text_content is not null;

commit;
