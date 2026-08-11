begin;

create function api.get_public_querido_diario_coverage(
  page_size integer default 31,
  page_offset integer default 0
)
returns table (
  coverage_day date,
  coverage_status text,
  preserved_editions bigint,
  preserved_documents bigint
)
language plpgsql stable security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 366 then
    raise exception 'page_size deve estar entre 1 e 366' using errcode = '22023';
  end if;
  if page_offset < 0 or page_offset > 5000 then
    raise exception 'page_offset deve estar entre 0 e 5000' using errcode = '22023';
  end if;

  return query
  select coverage.day,
    case
      when coverage.attempted_by_recorded_window
        and coverage.preserved_editions > 0 then 'complete'
      when coverage.attempted_by_recorded_window then 'empty'
      else 'unclassified'
    end,
    coverage.preserved_editions,
    coverage.preserved_documents
  from source.querido_diario_daily_coverage as coverage
  order by coverage.day desc
  limit page_size offset page_offset;
end;
$function$;

revoke all on function api.get_public_querido_diario_coverage(integer, integer)
  from public;
grant execute on function api.get_public_querido_diario_coverage(integer, integer)
  to anon, authenticated;
comment on function api.get_public_querido_diario_coverage(integer, integer) is
  'Resumo público das janelas diárias do Querido Diário; não confunde dia não classificado com dia vazio.';

commit;
