begin;

-- Linter de desempenho do Supabase (08/10/2026): duas chaves estrangeiras sem
-- índice em schemas que o teste de fundação não cobre (political, territory).
create index if not exists historical_representative_aliases_source_suggestion_idx
  on political.historical_representative_aliases (source_suggestion_id);

create index if not exists bahia_state_execution_annual_coverage_snapshot_job_idx
  on territory.bahia_state_execution_annual_coverage_snapshot (extraction_job_id);

commit;
