begin;

-- A busca de edições pendentes de extração de atos
-- (PostgresExtractionRepository.pending_text_artifacts) passou do
-- statement_timeout de 15 s do coletor em 24/09, com o dreno de OCR gravando
-- milhares de páginas. Aquecida, levava 4,4 s: varria os 52 mil artefatos
-- filtrando JSON e, para cada edição, lia as páginas inteiras (com o texto)
-- só para achar o horário do OCR mais recente.

-- Só os documentos do Diário (TXT do Querido Diário e PDF direto); o
-- predicado repete o da consulta para o planejador usar o índice.
create index raw_artifacts_gazette_text_documents_idx
  on raw.raw_artifacts (created_at, id)
  where artifact_kind = 'document'
    and (
      metadata ->> 'document_role' = 'txt'
      or metadata ->> 'schema_name' = 'gazette-direct-edition'
    );

-- max(created_at) das páginas OCR por artefato sem ler o texto das páginas.
create index document_pages_ocr_created_idx
  on raw.document_pages (raw_artifact_id, created_at)
  where extraction_method = 'ocr';

commit;
