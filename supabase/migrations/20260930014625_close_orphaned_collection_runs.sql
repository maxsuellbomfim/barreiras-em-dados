begin;

-- Execuções cujo processo morreu (job cancelado por tempo, máquina suspensa)
-- ficam para sempre como 'running': o sinal de vida só é gravado no início e
-- no fim. Em 30/09 eram 42, desde agosto. Nenhuma execução legítima passou de
-- 12 h nos últimos 60 dias (a mais longa válida levou ~3 h), então 24 h sem
-- sinal de vida é abandono. A execução vira 'cancelled' com motivo e
-- auditoria; a partição é refeita pelo próprio agendamento. Se o processo
-- voltar depois, a conclusão dele sobrescreve este status com o resultado
-- real.

create function source.close_orphaned_collection_runs()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  closed integer;
begin
  perform pg_advisory_xact_lock(hashtext('close-orphaned-collection-runs'));
  with orphaned as (
    update source.collection_runs as run
    set status = 'cancelled',
        completed_at = statement_timestamp(),
        error_code = 'OrphanedRun',
        error_detail = 'Execução sem sinal de vida por mais de 24 h; o '
          || 'processo terminou sem declarar cobertura (job cancelado ou '
          || 'máquina suspensa). A partição é refeita pelo agendamento.'
    where run.status = 'running'
      and coalesce(run.heartbeat_at, run.started_at, run.created_at)
        < statement_timestamp() - interval '24 hours'
    returning run.id
  )
  select count(*)::integer into closed from orphaned;

  if closed > 0 then
    insert into audit.audit_events (
      actor_type, actor_subject, action, target_type, target_id,
      after_state, metadata
    ) values (
      'worker',
      'close-orphaned-collection-runs',
      'collection_runs.orphans_closed',
      'source.collection_runs',
      null,
      jsonb_build_object('status', 'cancelled', 'count', closed),
      jsonb_build_object(
        'version', 'orphaned-collection-runs/1.0.0',
        'idle_threshold', '24 hours',
        'records_deleted', false
      )
    );
  end if;
  return closed;
end;
$$;

revoke all on function source.close_orphaned_collection_runs()
  from public, anon, authenticated, service_role;
grant execute on function source.close_orphaned_collection_runs()
  to collector_worker;

commit;
