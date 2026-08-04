-- O publicador registra falhas de parsing como novas tentativas do mesmo job.
-- O worker não recebe UPDATE geral: somente as colunas operacionais da DLQ.

grant update (
  status,
  attempt_count,
  last_error_code,
  last_error_detail,
  updated_at
) on raw.extraction_jobs to collector_worker;

create policy collector_worker_extraction_jobs_update
  on raw.extraction_jobs
  for update to collector_worker
  using (true)
  with check (true);
