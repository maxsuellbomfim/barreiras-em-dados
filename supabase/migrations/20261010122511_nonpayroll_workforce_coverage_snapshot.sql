begin;

-- A cobertura de estagiÃ¡rios e terceirizados (/financas/pessoal) recalcula a
-- cada visita a deduplicaÃ§Ã£o do catÃ¡logo e a procura dos PDFs: 3,4 s com
-- cache quente em 10/10/2026, acima dos 3 s do papel anÃ´nimo (cancelada nas
-- janelas da sonda pÃºblica). Os nÃºmeros sÃ³ mudam quando a coleta traz
-- catÃ¡logo ou PDF novo. Um instantÃ¢neo do cÃ¡lculo de 120 meses Ã© refeito de
-- hora em hora pelo pg_cron; o limite N devolve as 2N primeiras linhas (meses
-- em ordem decrescente, duas categorias), igual ao cÃ¡lculo ao vivo. Sem
-- instantÃ¢neo, cai no cÃ¡lculo ao vivo. Cache de leitura, nÃ£o registro.
alter function api.get_public_nonpayroll_workforce_coverage(integer)
  rename to get_public_nonpayroll_workforce_coverage_calculated;
revoke all on function api.get_public_nonpayroll_workforce_coverage_calculated(integer)
  from public, anon, authenticated;

create table finance.nonpayroll_workforce_coverage_snapshot (
  row_order integer primary key check (row_order between 1 and 240),
  reference_month text not null,
  workforce_category text not null,
  category_label text not null,
  coverage_status text not null,
  coverage_note text not null,
  catalog_document_count integer not null,
  preserved_document_count integer not null,
  source_url text,
  artifact_sha256 text,
  catalog_checked_at timestamptz,
  methodology_version text not null
);

-- SÃ³ Ã© servido depois de calculado (inclusive quando vazio).
create table finance.nonpayroll_workforce_coverage_snapshot_state (
  singleton boolean primary key default true check (singleton),
  row_count integer not null check (row_count >= 0),
  computed_at timestamptz not null
);

alter table finance.nonpayroll_workforce_coverage_snapshot enable row level security;
alter table finance.nonpayroll_workforce_coverage_snapshot force row level security;
alter table finance.nonpayroll_workforce_coverage_snapshot_state enable row level security;
alter table finance.nonpayroll_workforce_coverage_snapshot_state force row level security;
revoke all on finance.nonpayroll_workforce_coverage_snapshot from public, anon, authenticated;
revoke all on finance.nonpayroll_workforce_coverage_snapshot_state from public, anon, authenticated;

comment on table finance.nonpayroll_workforce_coverage_snapshot is
  'InstantÃ¢neo de api.get_public_nonpayroll_workforce_coverage_calculated(120), refeito de hora em hora; cache de leitura, nÃ£o registro.';

create function finance.refresh_nonpayroll_workforce_coverage_snapshot()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  refreshed integer;
begin
  perform pg_advisory_xact_lock(hashtext('finance.nonpayroll_workforce_coverage_snapshot'));
  delete from finance.nonpayroll_workforce_coverage_snapshot;
  delete from finance.nonpayroll_workforce_coverage_snapshot_state;
  insert into finance.nonpayroll_workforce_coverage_snapshot (
    row_order, reference_month, workforce_category, category_label,
    coverage_status, coverage_note, catalog_document_count,
    preserved_document_count, source_url, artifact_sha256,
    catalog_checked_at, methodology_version
  )
  select
    calculated.row_order::integer, calculated.reference_month,
    calculated.workforce_category, calculated.category_label,
    calculated.coverage_status, calculated.coverage_note,
    calculated.catalog_document_count, calculated.preserved_document_count,
    calculated.source_url, calculated.artifact_sha256,
    calculated.catalog_checked_at, calculated.methodology_version
  from api.get_public_nonpayroll_workforce_coverage_calculated(120)
    with ordinality as calculated(
      reference_month, workforce_category, category_label, coverage_status,
      coverage_note, catalog_document_count, preserved_document_count,
      source_url, artifact_sha256, catalog_checked_at, methodology_version,
      row_order
    );
  get diagnostics refreshed = row_count;
  insert into finance.nonpayroll_workforce_coverage_snapshot_state (row_count, computed_at)
  values (refreshed, statement_timestamp());
  return refreshed;
end;
$function$;

revoke all on function finance.refresh_nonpayroll_workforce_coverage_snapshot()
  from public, anon, authenticated;

create function api.get_public_nonpayroll_workforce_coverage(month_limit integer default 120)
returns table (
  reference_month text,
  workforce_category text,
  category_label text,
  coverage_status text,
  coverage_note text,
  catalog_document_count integer,
  preserved_document_count integer,
  source_url text,
  artifact_sha256 text,
  catalog_checked_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
#variable_conflict use_column
begin
  if month_limit is null or month_limit < 1 or month_limit > 120 then
    raise exception 'limite de cobertura de vÃ­nculos separados invÃ¡lido'
      using errcode = '22023';
  end if;
  if exists (select 1 from finance.nonpayroll_workforce_coverage_snapshot_state) then
    return query
    select
      snapshot.reference_month, snapshot.workforce_category,
      snapshot.category_label, snapshot.coverage_status, snapshot.coverage_note,
      snapshot.catalog_document_count, snapshot.preserved_document_count,
      snapshot.source_url, snapshot.artifact_sha256,
      snapshot.catalog_checked_at, snapshot.methodology_version
    from finance.nonpayroll_workforce_coverage_snapshot as snapshot
    order by snapshot.row_order
    limit month_limit * 2;
    return;
  end if;
  return query
  select * from api.get_public_nonpayroll_workforce_coverage_calculated(month_limit);
end;
$function$;

revoke all on function api.get_public_nonpayroll_workforce_coverage(integer) from public;
grant execute on function api.get_public_nonpayroll_workforce_coverage(integer)
  to anon, authenticated;

do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-nonpayroll-workforce-coverage-snapshot', '45 * * * *',
      'select finance.refresh_nonpayroll_workforce_coverage_snapshot()');
  end if;
end;
$schedule$;

notify pgrst, 'reload schema';

commit;
