-- Resumo determinístico de fornecedores vencedores no PNCP.
-- Concentração é contexto investigativo, não prova de irregularidade.

drop function if exists api.get_public_supplier_concentration(integer);

create function api.get_public_supplier_concentration(page_size integer default 30)
returns table (
  supplier_key text,
  supplier_name text,
  supplier_type text,
  public_registration_number text,
  procurement_count integer,
  item_count integer,
  total_awarded_amount numeric,
  awarded_share numeric,
  first_result_date date,
  last_result_date date,
  attention_signal boolean,
  public_explanation text,
  source_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
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
  supplier_rows as (
    select
      coalesce(nullif(row.payload ->> 'niFornecedor', ''),
        lower(regexp_replace(row.payload ->> 'nomeRazaoSocialFornecedor', '[^[:alnum:]]', '', 'g'))
      ) as supplier_key,
      row.payload ->> 'nomeRazaoSocialFornecedor' as supplier_name,
      coalesce(row.payload ->> 'tipoPessoa', 'unknown') as supplier_type,
      case when row.payload ->> 'tipoPessoa' = 'PJ'
        then nullif(row.payload ->> 'niFornecedor', '')
      end as public_registration_number,
      row.payload ->> 'numeroControlePNCPCompra' as control_number,
      (row.payload ->> 'valorTotalHomologado')::numeric as awarded_amount,
      case
        when row.payload ->> 'dataResultado' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        then left(row.payload ->> 'dataResultado', 10)::date
      end as result_date,
      row.source_url
    from latest_results as row
  ),
  grouped as (
    select
      supplier_rows.supplier_key,
      max(supplier_rows.supplier_name) as supplier_name,
      max(supplier_rows.supplier_type) as supplier_type,
      max(supplier_rows.public_registration_number) as public_registration_number,
      count(distinct supplier_rows.control_number)::integer as procurement_count,
      count(*)::integer as item_count,
      sum(supplier_rows.awarded_amount) as total_awarded_amount,
      min(supplier_rows.result_date) as first_result_date,
      max(supplier_rows.result_date) as last_result_date,
      max(supplier_rows.source_url) as source_url
    from supplier_rows
    group by supplier_rows.supplier_key
  ),
  with_share as (
    select
      grouped.*,
      grouped.total_awarded_amount / nullif(sum(grouped.total_awarded_amount) over (), 0) as awarded_share
    from grouped
  )
  select
    with_share.supplier_key,
    with_share.supplier_name,
    with_share.supplier_type,
    with_share.public_registration_number,
    with_share.procurement_count,
    with_share.item_count,
    with_share.total_awarded_amount,
    round(with_share.awarded_share, 6),
    with_share.first_result_date,
    with_share.last_result_date,
    (with_share.procurement_count >= 3 or with_share.awarded_share >= 0.5),
    case
      when with_share.procurement_count >= 3 or with_share.awarded_share >= 0.5
        then 'Este fornecedor concentra vários itens/processos ou parcela relevante do valor homologado na janela observada. É um sinal para contextualização, não prova de irregularidade.'
      else 'Resumo dos resultados homologados preservados no PNCP para esta janela. O número não mede qualidade, legalidade ou desempenho do fornecedor.'
    end,
    with_share.source_url,
    'pncp-supplier-concentration/1.0.0'::text
  from with_share
  order by with_share.total_awarded_amount desc, with_share.supplier_name
  limit page_size;
end;
$function$;

revoke all on function api.get_public_supplier_concentration(integer) from public;
grant execute on function api.get_public_supplier_concentration(integer)
  to anon, authenticated;

comment on function api.get_public_supplier_concentration(integer) is
  'Resumo determinístico de fornecedores e concentração observada nos resultados PNCP; não é acusação.';
