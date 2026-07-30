-- A mesma sequência de bytes pode ser observada em URLs ou execuções
-- diferentes. O objeto é compartilhado por chave de conteúdo, mas cada
-- observação continua sendo um raw_artifact imutável.
alter table raw.raw_artifacts
  drop constraint raw_artifacts_object_key_key;

create index raw_artifacts_object_key_idx
  on raw.raw_artifacts (object_key);

create index raw_artifacts_collection_run_idx
  on raw.raw_artifacts (collection_run_id);

create index raw_artifacts_parent_idx
  on raw.raw_artifacts (parent_artifact_id)
  where parent_artifact_id is not null;

-- Uma nova versão do parser deve poder produzir uma nova visão estruturada do
-- mesmo artefato sem apagar a versão anterior.
alter table raw.raw_records
  drop constraint raw_records_raw_artifact_id_record_index_key;

alter table raw.raw_records
  add constraint raw_records_artifact_index_parser_key
  unique (raw_artifact_id, record_index, parser_version);

-- Papel-base sem login. O login real e sua senha são provisionados fora da
-- migration e recebem somente este papel.
do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'collector_worker'
  ) then
    create role collector_worker nologin nosuperuser nocreatedb
      nocreaterole noinherit noreplication;
  end if;
end
$$;

alter role collector_worker set statement_timeout = '15s';
alter role collector_worker set lock_timeout = '5s';
alter role collector_worker set idle_in_transaction_session_timeout = '15s';

grant usage on schema source, raw to collector_worker;

grant select on table
  source.data_sources,
  source.source_endpoints,
  source.collection_runs
to collector_worker;

grant insert (
  source_endpoint_id,
  idempotency_key,
  collector_version,
  parser_version,
  collection_window_start,
  collection_window_end,
  cursor_before,
  cursor_after,
  status,
  attempt_count,
  started_at,
  completed_at,
  heartbeat_at,
  metrics,
  error_code,
  error_detail
) on source.collection_runs to collector_worker;

grant update (
  status,
  attempt_count,
  cursor_after,
  completed_at,
  heartbeat_at,
  metrics,
  error_code,
  error_detail
) on source.collection_runs to collector_worker;

grant select on table
  raw.raw_artifacts,
  raw.raw_records
to collector_worker;

grant insert (
  collection_run_id,
  source_endpoint_id,
  parent_artifact_id,
  idempotency_key,
  artifact_kind,
  source_url,
  retrieved_at,
  source_published_at,
  source_last_modified_at,
  source_etag,
  http_status,
  content_type,
  byte_size,
  sha256,
  object_key,
  collector_version,
  parser_version,
  response_headers,
  metadata
) on raw.raw_artifacts to collector_worker;

grant insert (
  raw_artifact_id,
  source_record_key,
  record_type,
  record_index,
  payload,
  payload_sha256,
  parser_version,
  idempotency_key,
  collected_at
) on raw.raw_records to collector_worker;
