begin;

-- As tabelas internas nunca são uma superfície pública do portal: a API
-- expõe somente funções/projeções no schema api. RLS acrescenta uma segunda
-- barreira caso um privilégio seja concedido por engano no futuro.
do $$
declare
  relation_record record;
begin
  for relation_record in
    select schemaname, tablename
    from pg_catalog.pg_tables
    where schemaname in (
      'source', 'raw', 'org', 'hr', 'procurement', 'finance',
      'evidence', 'analysis', 'editorial', 'audit'
    )
  loop
    execute format(
      'alter table %I.%I enable row level security',
      relation_record.schemaname,
      relation_record.tablename
    );

    execute format(
      'revoke all on table %I.%I from public, anon, authenticated',
      relation_record.schemaname,
      relation_record.tablename
    );
  end loop;
end
$$;

-- O coletor usa uma identidade técnica sem login direto e herda
-- collector_worker. As políticas repetem exatamente os grants mínimos já
-- provisionados; nenhuma outra role recebe acesso por este migration.
create policy collector_worker_source_data_sources_select
on source.data_sources
for select to collector_worker
using (true);

create policy collector_worker_source_endpoints_select
on source.source_endpoints
for select to collector_worker
using (true);

create policy collector_worker_collection_runs_select
on source.collection_runs
for select to collector_worker
using (true);

create policy collector_worker_collection_runs_insert
on source.collection_runs
for insert to collector_worker
with check (true);

create policy collector_worker_collection_runs_update
on source.collection_runs
for update to collector_worker
using (true)
with check (true);

create policy collector_worker_raw_artifacts_select
on raw.raw_artifacts
for select to collector_worker
using (true);

create policy collector_worker_raw_artifacts_insert
on raw.raw_artifacts
for insert to collector_worker
with check (true);

create policy collector_worker_raw_records_select
on raw.raw_records
for select to collector_worker
using (true);

create policy collector_worker_raw_records_insert
on raw.raw_records
for insert to collector_worker
with check (true);

create policy collector_worker_document_pages_select
on raw.document_pages
for select to collector_worker
using (true);

create policy collector_worker_document_pages_insert
on raw.document_pages
for insert to collector_worker
with check (true);

create policy collector_worker_extraction_jobs_select
on raw.extraction_jobs
for select to collector_worker
using (true);

create policy collector_worker_extraction_jobs_insert
on raw.extraction_jobs
for insert to collector_worker
with check (true);

create policy collector_worker_extraction_results_select
on raw.extraction_results
for select to collector_worker
using (true);

create policy collector_worker_extraction_results_insert
on raw.extraction_results
for insert to collector_worker
with check (true);

create policy collector_worker_editorial_reviews_select
on editorial.editorial_reviews
for select to collector_worker
using (true);

comment on schema source is
  'Internal source catalog. RLS is enabled; public reads use schema api projections.';
comment on schema raw is
  'Immutable evidence. RLS is enabled; collector access is limited to its explicit policies.';
comment on schema editorial is
  'Review and publication workflow. RLS is enabled; decisions remain behind reviewed functions.';

commit;
