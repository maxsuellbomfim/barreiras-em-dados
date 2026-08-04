-- Histórico navegável de processos por fornecedor no PNCP.
-- O identificador público é CNPJ quando disponível; pessoas físicas nunca
-- recebem número de documento nesta projeção.

drop function if exists api.get_public_supplier_history(text, integer);

create function api.get_public_supplier_history(
  supplier_key_filter text,
  page_size integer default 100
)
returns table (
  supplier_key text,
  supplier_name text,
  supplier_type text,
  control_number text,
  object_description text,
  publication_date date,
  result_date date,
  item_count integer,
  total_awarded_amount numeric,
  source_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if supplier_key_filter is null or length(trim(supplier_key_filter)) = 0
     or length(supplier_key_filter) > 200 then
    raise exception 'supplier_key_filter inválido'
      using errcode = '22023';
  end if;
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  with latest_results as (
    select distinct on (
      result.payload ->> 'numeroControlePNCPCompra',
      result.payload ->> 'numeroItem',
      result.payload ->> 'sequencialResultado'
    )
      result.payload,
      artifact.source_url
    from raw.raw_records as result
    join raw.raw_artifacts as artifact on artifact.id = result.raw_artifact_id
    where result.record_type = 'pncp_resultado'
      and result.payload ->> 'numeroControlePNCPCompra' is not null
      and result.payload ->> 'nomeRazaoSocialFornecedor' is not null
      and result.payload ->> 'valorTotalHomologado' ~ '^[0-9]+(\.[0-9]+)?$'
      and result.payload ->> 'numeroItem' ~ '^[0-9]+$'
    order by
      result.payload ->> 'numeroControlePNCPCompra',
      result.payload ->> 'numeroItem',
      result.payload ->> 'sequencialResultado',
      result.created_at desc,
      result.id desc
  ),
  rows as (
    select
      coalesce(nullif(result.payload ->> 'niFornecedor', ''),
        lower(regexp_replace(result.payload ->> 'nomeRazaoSocialFornecedor', '[^[:alnum:]]', '', 'g'))
      ) as supplier_key,
      result.payload ->> 'nomeRazaoSocialFornecedor' as supplier_name,
      coalesce(result.payload ->> 'tipoPessoa', 'unknown') as supplier_type,
      result.payload ->> 'numeroControlePNCPCompra' as control_number,
      (result.payload ->> 'valorTotalHomologado')::numeric as awarded_amount,
      case
        when result.payload ->> 'dataResultado' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        then left(result.payload ->> 'dataResultado', 10)::date
      end as result_date,
      result.source_url,
      procurement.payload ->> 'objetoCompra' as object_description,
      case
        when procurement.payload ->> 'dataPublicacaoPncp' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        then left(procurement.payload ->> 'dataPublicacaoPncp', 10)::date
      end as publication_date,
      result.payload ->> 'numeroItem' as item_number
    from latest_results as result
    left join lateral (
      select record.payload
      from raw.raw_records as record
      where record.record_type = 'pncp_contratacao'
        and record.payload ->> 'numeroControlePNCP' = result.payload ->> 'numeroControlePNCPCompra'
      order by record.created_at desc, record.id desc
      limit 1
    ) as procurement on true
  )
  select
    rows.supplier_key,
    max(rows.supplier_name),
    max(rows.supplier_type),
    rows.control_number,
    max(rows.object_description),
    max(rows.publication_date),
    max(rows.result_date),
    count(*)::integer,
    sum(rows.awarded_amount),
    max(rows.source_url),
    'pncp-supplier-history/1.0.0'::text
  from rows
  where rows.supplier_key = trim(supplier_key_filter)
  group by rows.supplier_key, rows.control_number
  order by max(rows.result_date) desc nulls last, rows.control_number
  limit page_size;
end;
$function$;

revoke all on function api.get_public_supplier_history(text, integer) from public;
grant execute on function api.get_public_supplier_history(text, integer)
  to anon, authenticated;

comment on function api.get_public_supplier_history(text, integer) is
  'Histórico público de processos PNCP por fornecedor, com itens, valores e fonte.';
