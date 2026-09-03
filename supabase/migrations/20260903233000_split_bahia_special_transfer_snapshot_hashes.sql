begin;

-- A coleta recorrente renova identificadores e timestamps de linhagem mesmo
-- quando os fatos oficiais permanecem idênticos. O refresh continua
-- conferindo a cópia integral, mas passa a registrar separadamente o hash
-- semântico usado para detectar mudanças no conteúdo publicado.
create or replace function territory.refresh_bahia_special_transfer_payment_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  live_rows integer;
  refreshed_rows integer;
  live_lineage_payload text;
  snapshot_lineage_payload text;
  live_semantic_payload text;
  snapshot_semantic_payload text;
  live_lineage_manifest text;
  snapshot_lineage_manifest text;
  live_semantic_manifest text;
  snapshot_semantic_manifest text;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'territory.bahia_special_transfer_payment_snapshot',
      0
    )
  );

  select
    count(*),
    coalesce(
      jsonb_agg(
        to_jsonb(source_row)
        order by source_row.payment_id
      ),
      '[]'::jsonb
    )::text,
    coalesce(
      jsonb_agg(
        to_jsonb(source_row)
          - 'extraction_result_id'
          - 'raw_artifact_id'
          - 'source_artifact_sha256'
          - 'source_collected_at'
          - 'result_created_at'
        order by source_row.payment_id
      ),
      '[]'::jsonb
    )::text
  into live_rows, live_lineage_payload, live_semantic_payload
  from territory.latest_bahia_special_transfer_payment_candidates_live
    as source_row;

  live_lineage_manifest := encode(
    pg_catalog.sha256(convert_to(live_lineage_payload, 'UTF8')),
    'hex'
  );
  live_semantic_manifest := encode(
    pg_catalog.sha256(convert_to(live_semantic_payload, 'UTF8')),
    'hex'
  );

  delete from territory.bahia_special_transfer_payment_snapshot;

  insert into territory.bahia_special_transfer_payment_snapshot
  select *
  from territory.latest_bahia_special_transfer_payment_candidates_live;

  get diagnostics refreshed_rows = row_count;

  select
    coalesce(
      jsonb_agg(
        to_jsonb(snapshot_row)
        order by snapshot_row.payment_id
      ),
      '[]'::jsonb
    )::text,
    coalesce(
      jsonb_agg(
        to_jsonb(snapshot_row)
          - 'extraction_result_id'
          - 'raw_artifact_id'
          - 'source_artifact_sha256'
          - 'source_collected_at'
          - 'result_created_at'
        order by snapshot_row.payment_id
      ),
      '[]'::jsonb
    )::text
  into snapshot_lineage_payload, snapshot_semantic_payload
  from territory.bahia_special_transfer_payment_snapshot as snapshot_row;

  snapshot_lineage_manifest := encode(
    pg_catalog.sha256(convert_to(snapshot_lineage_payload, 'UTF8')),
    'hex'
  );
  snapshot_semantic_manifest := encode(
    pg_catalog.sha256(convert_to(snapshot_semantic_payload, 'UTF8')),
    'hex'
  );

  if refreshed_rows <> live_rows
     or snapshot_lineage_manifest is distinct from live_lineage_manifest
     or snapshot_semantic_manifest is distinct from live_semantic_manifest
  then
    raise exception
      'Snapshot de pagamentos estaduais especiais divergiu da fonte canonica: fonte=%, snapshot=%',
      live_rows,
      refreshed_rows;
  end if;

  insert into audit.audit_events (
    actor_type,
    actor_subject,
    action,
    target_type,
    target_id,
    after_state,
    metadata
  )
  values (
    'system',
    'worker:bahia-special-transfers',
    'source_snapshot.refreshed',
    'territory.bahia_special_transfer_payment_snapshot',
    gen_random_uuid(),
    jsonb_build_object(
      'row_count', refreshed_rows,
      -- Compatibilidade com leitores anteriores: o hash integral continua
      -- disponível sob o nome original e também sob o nome explícito.
      'content_sha256', snapshot_lineage_manifest,
      'lineage_content_sha256', snapshot_lineage_manifest,
      'semantic_content_sha256', snapshot_semantic_manifest,
      'methodology_version',
      'bahia-special-transfer-payment-snapshot/1.1.0'
    ),
    jsonb_build_object(
      'source_projection',
      'territory.latest_bahia_special_transfer_payment_candidates_live',
      'raw_json_recomputed_per_public_request', false,
      'lineage_hash_scope', 'all_snapshot_columns',
      'semantic_hash_excludes', jsonb_build_array(
        'extraction_result_id',
        'raw_artifact_id',
        'source_artifact_sha256',
        'source_collected_at',
        'result_created_at'
      )
    )
  );

  return refreshed_rows;
end;
$$;

comment on function
  territory.refresh_bahia_special_transfer_payment_snapshot() is
  'Atualiza atomicamente os pagamentos estaduais especiais e audita separadamente conteudo publico e linhagem tecnica.';

select territory.refresh_bahia_special_transfer_payment_snapshot();

commit;
