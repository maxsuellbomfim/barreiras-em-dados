begin;

-- Contexto estatístico conservador para itens literalmente equivalentes.
-- Não é uma regra de sobrepreço: apenas informa a dispersão observada no PNCP.
create or replace function api.get_pncp_item_price_context(
  page_size integer default 1000
)
returns table (
  descricao text,
  unidade text,
  observacoes integer,
  minimo numeric,
  mediana numeric,
  maximo numeric,
  methodology_version text
)
language plpgsql
stable
security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 1000 then
    raise exception 'page_size deve estar entre 1 e 1000' using errcode = '22023';
  end if;

  return query
  select
    item.description,
    item.unit_name,
    count(*)::integer,
    min(item.estimated_unit_amount),
    percentile_cont(0.5) within group (order by item.estimated_unit_amount)::numeric,
    max(item.estimated_unit_amount),
    'pncp-price-context/1.0.0'::text
  from procurement.procurement_items as item
  where item.description is not null
    and length(trim(item.description)) > 0
    and item.unit_name is not null
    and length(trim(item.unit_name)) > 0
    and item.estimated_unit_amount is not null
    and item.estimated_unit_amount > 0
    and not exists (
      select 1
      from procurement.procurement_items as newer
      where newer.supersedes_id = item.id
    )
  group by item.description, item.unit_name
  having count(distinct item.procurement_id) >= 2
  order by count(*) desc, item.description, item.unit_name
  limit page_size;
end;
$function$;

revoke all on function api.get_pncp_item_price_context(integer) from public, anon, authenticated;
grant execute on function api.get_pncp_item_price_context(integer) to anon, authenticated;

comment on function api.get_pncp_item_price_context(integer) is
  'Contexto estatístico de valores unitários estimados para descrições e unidades literalmente iguais; não é conclusão de irregularidade.';

commit;
