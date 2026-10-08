begin;

-- A fila de reorganização do Diário precisa da página mais nova de cada
-- edição (1.470 edições, 58 mil páginas depois do backfill de 2021-2022).
-- Com o índice por (artefato, página, criação) ela lia todas as entradas;
-- por (artefato, criação desc) responde com uma sonda por edição.
create index if not exists document_pages_artifact_created_idx
  on raw.document_pages (raw_artifact_id, created_at desc);

commit;
