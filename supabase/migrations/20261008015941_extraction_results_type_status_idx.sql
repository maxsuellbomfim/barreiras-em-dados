begin;

-- raw.extraction_results passou de 246 mil linhas (216 mil são agregados da
-- execução estadual) e não tinha índice por tipo de candidato. A cobertura de
-- restos a pagar varria a tabela inteira (1,7 s) para achar 15 linhas, em
-- toda visita a Finanças; atos, resumos de edição e fila de revisão filtram
-- pelo mesmo par (tipo, estado de validação).
create index if not exists extraction_results_type_status_idx
  on raw.extraction_results (candidate_type, validation_status, created_at desc);

commit;
