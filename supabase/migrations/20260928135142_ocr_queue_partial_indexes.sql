begin;

-- A fila de OCR relia ~18 mil páginas "só número" já resolvidas por OCR para
-- descartá-las, com leitura fria da tabela inteira; passava do
-- statement_timeout de 15 s do coletor (falhas de 25 e 26/09 no workflow de
-- atos). Dois índices parciais pequenos permitem achar o que ainda falta
-- somente pelo índice, antes de aplicar as regras completas da fila.

-- Páginas que podem precisar de OCR: sem texto ou só com o número da página.
create index if not exists document_pages_ocr_candidates_idx
  on raw.document_pages (raw_artifact_id, page_number)
  where text_content is null
     or (
       extraction_method <> 'ocr'
       and octet_length(text_content) <= 64
       and btrim(text_content) = page_number::text
     );

-- Páginas que já têm texto de OCR.
create index if not exists document_pages_ocr_done_idx
  on raw.document_pages (raw_artifact_id, page_number)
  where extraction_method = 'ocr' and text_content is not null;

commit;
