begin;

-- Sete RPCs públicas de finanças (receitas, despesas, folha, cobertura e
-- fechamento mensal) recalculavam a cada visita os pares de linhagem exata
-- documento-origem. A parte do TCM-BA percorre todos os PDFs mensais (23 mil
-- em 13/10/2026, crescendo ~800 por dia): com cache frio, foi a consulta
-- pública mais cancelada pelos 3 s do papel anônimo (54 vezes em 24 h).
-- Os pares só mudam quando a coleta preserva documento novo. Um instantâneo é
-- refeito a cada 10 minutos pelo pg_cron; sem instantâneo, cai no cálculo ao
-- vivo, com as mesmas regras. Cache de leitura, não registro: a regra continua
-- em finance.get_exact_document_lineage_pairs_calculated().
alter function finance.get_exact_document_lineage_pairs()
  rename to get_exact_document_lineage_pairs_calculated;

create table finance.exact_document_lineage_pairs_snapshot (
  origin_raw_record_id uuid not null,
  document_artifact_id uuid not null,
  primary key (origin_raw_record_id, document_artifact_id)
);

create table finance.exact_document_lineage_pairs_snapshot_state (
  singleton boolean primary key default true check (singleton),
  row_count integer not null check (row_count >= 0),
  computed_at timestamptz not null
);

alter table finance.exact_document_lineage_pairs_snapshot enable row level security;
alter table finance.exact_document_lineage_pairs_snapshot force row level security;
alter table finance.exact_document_lineage_pairs_snapshot_state enable row level security;
alter table finance.exact_document_lineage_pairs_snapshot_state force row level security;
revoke all on finance.exact_document_lineage_pairs_snapshot from public, anon, authenticated;
revoke all on finance.exact_document_lineage_pairs_snapshot_state from public, anon, authenticated;

comment on table finance.exact_document_lineage_pairs_snapshot is
  'Instantâneo de finance.get_exact_document_lineage_pairs_calculated(), refeito a cada 10 minutos; cache de leitura, não registro.';

create function finance.refresh_exact_document_lineage_pairs_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  refreshed integer;
begin
  perform pg_advisory_xact_lock(hashtext('finance.exact_document_lineage_pairs_snapshot'));
  delete from finance.exact_document_lineage_pairs_snapshot;
  delete from finance.exact_document_lineage_pairs_snapshot_state;
  insert into finance.exact_document_lineage_pairs_snapshot (
    origin_raw_record_id, document_artifact_id
  )
  select calculated.origin_raw_record_id, calculated.document_artifact_id
  from finance.get_exact_document_lineage_pairs_calculated() as calculated;
  get diagnostics refreshed = row_count;
  insert into finance.exact_document_lineage_pairs_snapshot_state (row_count, computed_at)
  values (refreshed, statement_timestamp());
  return refreshed;
end;
$function$;

revoke all on function finance.refresh_exact_document_lineage_pairs_snapshot()
  from public, anon, authenticated;

create function finance.get_exact_document_lineage_pairs()
returns table (origin_raw_record_id uuid, document_artifact_id uuid)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if exists (select 1 from finance.exact_document_lineage_pairs_snapshot_state) then
    return query
    select snapshot.origin_raw_record_id, snapshot.document_artifact_id
    from finance.exact_document_lineage_pairs_snapshot as snapshot;
    return;
  end if;
  return query
  select calculated.origin_raw_record_id, calculated.document_artifact_id
  from finance.get_exact_document_lineage_pairs_calculated() as calculated;
end;
$function$;

revoke all on function finance.get_exact_document_lineage_pairs() from public, anon, authenticated;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-exact-document-lineage-pairs-snapshot', '*/10 * * * *',
      'select finance.refresh_exact_document_lineage_pairs_snapshot()');
  end if;
end;
$schedule$;

commit;
