begin;

-- O índice de expressões não permitiu leitura só do índice (o planejador
-- ainda busca result_payload no heap); sem ganho, sai (10/10/2026).
drop index if exists raw.extraction_results_tcm_ba_family_coverage_idx;

commit;
