begin;

-- Não existe executor genérico de novas tentativas: cada coletor volta a
-- tentar pelo próprio agendamento. Só o caminho de execução controlada
-- fechava falhas antigas, então falhas já superadas ficavam para sempre como
-- 'retry_scheduled' com next_retry_at vencido. Esta reconciliação fecha
-- apenas falhas com evidência de recuperação, guarda o motivo e a execução
-- que a comprova, e registra auditoria. Nada é apagado.

alter table source.collection_failures
  add column resolution_reason text;

alter table source.collection_failures
  add constraint collection_failures_resolution_reason_check check (
    resolution_reason is null
    or (
      status = 'resolved'
      and resolution_reason in (
        'same_partition_recovered',
        'snapshot_superseded',
        'covered_by_primary_source'
      )
    )
  );

create function source.reconcile_collection_failures()
returns table (rule text, resolved_count integer)
language plpgsql
security definer
set search_path = ''
as $$
declare
  reconciliation_version constant text :=
    'collection-failure-reconciliation/1.0.0';
  same_partition integer;
  snapshot_superseded integer;
  covered_by_primary integer;
begin
  perform pg_advisory_xact_lock(hashtext('collection-failure-reconciliation'));

  -- 1. A mesma partição terminou completa ou vazia depois da falha.
  with evidence as (
    select distinct on (failure.id)
      failure.id, partition.collection_run_id
    from source.collection_failures as failure
    join source.collection_partitions as partition
      on partition.source_endpoint_id = failure.source_endpoint_id
     and partition.partition_key = failure.partition_key
    join source.collection_runs as run
      on run.id = partition.collection_run_id
    where failure.status <> 'resolved'
      and partition.status in ('complete', 'empty')
      and run.status = 'succeeded'
      and partition.completed_at > failure.failed_at
    order by failure.id
  ), updated as (
    update source.collection_failures as failure
    set status = 'resolved',
        resolved_at = statement_timestamp(),
        resolution_run_id = evidence.collection_run_id,
        resolution_reason = 'same_partition_recovered',
        next_retry_at = null,
        updated_at = statement_timestamp()
    from evidence
    where failure.id = evidence.id
    returning failure.id
  )
  select count(*)::integer into same_partition from updated;

  -- 2. Retratos datados (catálogo, arquivo, dia) não podem ser refeitos: a
  -- fonte já mudou. Um retrato posterior bem-sucedido do mesmo endpoint e do
  -- mesmo tipo substitui o que falhou.
  with evidence as (
    select distinct on (failure.id)
      failure.id, later.collection_run_id
    from source.collection_failures as failure
    join source.collection_partitions as later
      on later.source_endpoint_id = failure.source_endpoint_id
     and split_part(later.partition_key, ':', 1)
       = split_part(failure.partition_key, ':', 1)
     and later.partition_key <> failure.partition_key
    join source.collection_runs as run
      on run.id = later.collection_run_id
    where failure.status <> 'resolved'
      and failure.partition_key
        ~ '^(catalog-snapshot|archive-snapshot|day):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and later.partition_key
        ~ '^(catalog-snapshot|archive-snapshot|day):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and later.status in ('complete', 'empty')
      and run.status = 'succeeded'
      and later.completed_at > failure.failed_at
    order by failure.id, later.completed_at, later.collection_run_id
  ), updated as (
    update source.collection_failures as failure
    set status = 'resolved',
        resolved_at = statement_timestamp(),
        resolution_run_id = evidence.collection_run_id,
        resolution_reason = 'snapshot_superseded',
        next_retry_at = null,
        updated_at = statement_timestamp()
    from evidence
    where failure.id = evidence.id
    returning failure.id
  )
  select count(*)::integer into snapshot_superseded from updated;

  -- 3. A API do Querido Diário é complementar: a semana que ela não entregou
  -- já está coberta pelo catálogo oficial da Prefeitura, a mesma equivalência
  -- usada pela âncora do backfill.
  with evidence as (
    select distinct on (failure.id)
      failure.id, catalog.collection_run_id
    from source.collection_failures as failure
    join source.source_endpoints as endpoint
      on endpoint.id = failure.source_endpoint_id
    join source.data_sources as data_source
      on data_source.id = endpoint.data_source_id
    join source.collection_partitions as catalog
      on catalog.partition_key like 'catalog-window:%'
     and catalog.status in ('complete', 'empty')
     and catalog.period_start
       <= split_part(failure.partition_key, ':', 2)::date
     and catalog.period_end
       >= split_part(failure.partition_key, ':', 3)::date
    join source.source_endpoints as catalog_endpoint
      on catalog_endpoint.id = catalog.source_endpoint_id
     and catalog_endpoint.slug = 'catalogo-publicacoes'
    join source.data_sources as catalog_source
      on catalog_source.id = catalog_endpoint.data_source_id
     and catalog_source.slug = 'barreiras-diario-oficial'
    join source.collection_runs as run
      on run.id = catalog.collection_run_id
     and run.status = 'succeeded'
    where failure.status <> 'resolved'
      and data_source.slug = 'querido-diario'
      and endpoint.slug = 'gazettes-api'
      and failure.partition_key
        ~ '^published:[0-9]{4}-[0-9]{2}-[0-9]{2}:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    order by failure.id, catalog.completed_at, catalog.collection_run_id
  ), updated as (
    update source.collection_failures as failure
    set status = 'resolved',
        resolved_at = statement_timestamp(),
        resolution_run_id = evidence.collection_run_id,
        resolution_reason = 'covered_by_primary_source',
        next_retry_at = null,
        updated_at = statement_timestamp()
    from evidence
    where failure.id = evidence.id
    returning failure.id
  )
  select count(*)::integer into covered_by_primary from updated;

  if same_partition + snapshot_superseded + covered_by_primary > 0 then
    insert into audit.audit_events (
      actor_type, actor_subject, action, target_type, target_id,
      after_state, metadata
    ) values (
      'worker',
      'collection-failure-reconciliation',
      'collection_failures.reconciled',
      'source.collection_failures',
      null,
      jsonb_build_object(
        'same_partition_recovered', same_partition,
        'snapshot_superseded', snapshot_superseded,
        'covered_by_primary_source', covered_by_primary
      ),
      jsonb_build_object(
        'version', reconciliation_version,
        'records_deleted', false
      )
    );
  end if;

  return query values
    ('same_partition_recovered'::text, same_partition),
    ('snapshot_superseded'::text, snapshot_superseded),
    ('covered_by_primary_source'::text, covered_by_primary);
end;
$$;

revoke all on function source.reconcile_collection_failures()
  from public, anon, authenticated, service_role;
grant execute on function source.reconcile_collection_failures()
  to collector_worker;

commit;
