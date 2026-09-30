begin;

-- A chave de idempotência da extração de atos inclui o hash do texto quando
-- páginas vêm do OCR, então a fila não conseguia reconhecer, pela chave, que
-- a edição já tinha sido processada pela régua vigente: toda edição com OCR
-- voltava à fila em cada execução (75 edições, ~28 min por rodada desde
-- 27/09/2026). O job passa a registrar a versão da régua que o produziu.

alter table raw.extraction_jobs
  add column extractor_version text
  check (extractor_version is null or length(extractor_version) between 3 and 120);

comment on column raw.extraction_jobs.extractor_version is
  'Versão da régua que produziu o job; nula em jobs anteriores a 30/09/2026.';

-- O worker só atualiza colunas operacionais; a nova tentativa de um job que
-- falhou grava a régua que finalmente o concluiu.
grant update (extractor_version) on raw.extraction_jobs to collector_worker;

commit;
