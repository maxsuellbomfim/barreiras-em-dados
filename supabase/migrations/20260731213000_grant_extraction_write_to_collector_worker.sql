-- A fatia inicial da etapa 1B roda no mesmo workflow diário da coleta, com a
-- mesma identidade técnica. O papel collector_worker recebe somente SELECT e
-- INSERT nas tabelas de página canônica e fila de extração: sem UPDATE e sem
-- DELETE, o histórico continua imutável.
-- ponytail: papel único para coleta+processamento; separar um papel
-- processor_* quando houver worker independente do workflow diário.

grant select, insert on raw.document_pages to collector_worker;
grant select, insert on raw.extraction_jobs to collector_worker;
grant select, insert on raw.extraction_results to collector_worker;
