begin;

-- Cobertura diária do Diário: as edições diretas liam as 14,6 mil versões
-- de documento por varredura sequencial (≈0,9 s com cache quente em
-- 17/10/2026; 2,2 s frio). Índice de cobertura por artefato permite
-- varredura só-índice (≈0,14 s nesse trecho). Sem mudança de resultado.
create index if not exists gazette_document_versions_artifact_edition_idx
  on editorial.gazette_document_versions (raw_artifact_id)
  include (edition, edition_date);

commit;
