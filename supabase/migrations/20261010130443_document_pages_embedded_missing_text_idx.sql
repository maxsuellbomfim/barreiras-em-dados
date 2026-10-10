begin;

-- Páginas com texto embutido ausente (360 em 10/10/2026): a prontidão dos
-- PDFs do TCM-BA para empenhos e contratos sai deste índice pequeno, sem ler
-- o texto das 411 mil páginas embutidas nem o índice geral de candidatos a
-- OCR (36 mil entradas de outras fontes).
create index if not exists document_pages_embedded_missing_text_idx
  on raw.document_pages (raw_artifact_id, page_number)
  where parser_version = 'gazette-pdf-embedded-text/1.1.0'
    and text_content is null;

commit;
