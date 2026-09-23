begin;

-- Falhas HTTP permanentes (ex.: 404 do Querido Diário) eram gravadas como
-- 'retry_scheduled', mas não existe executor de novas tentativas e uma
-- resposta permanente não se resolve repetindo a mesma requisição. O coletor
-- passa a gravá-las como 'open'; esta migration corrige somente a
-- classificação das entradas já abertas, sem apagar nem resolver nada, e
-- registra a correção em auditoria.

with reclassified as (
  update source.collection_failures
  set status = 'open',
      retryable = false,
      next_retry_at = null,
      updated_at = statement_timestamp()
  where status = 'retry_scheduled'
    and resolved_at is null
    and error_type = 'PermanentHttpError'
  returning id
)
insert into audit.audit_events (
  actor_type, actor_subject, action, target_type, target_id,
  after_state, metadata
)
select
  'administrator',
  'migration:reclassify-permanent-collection-failures',
  'collection_failures.reclassified',
  'source.collection_failures',
  null,
  jsonb_build_object('status', 'open', 'retryable', false,
    'count', (select count(*) from reclassified)),
  jsonb_build_object(
    'reason', 'erro HTTP permanente não é elegível a nova tentativa',
    'records_deleted', false,
    'records_resolved', false
  );

commit;
