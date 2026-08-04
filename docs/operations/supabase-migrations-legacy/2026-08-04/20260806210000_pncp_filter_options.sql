-- Opções observadas nos registros PNCP preservados. Esta função não inventa
-- categorias: cada opção corresponde ao texto publicado pela fonte.

create function api.get_pncp_procurement_filter_options()
returns table (
  option_type text,
  option_value text,
  procurement_count bigint
)
language sql
stable
security definer set search_path = ''
as $function$
  with latest_contracts as (
    select distinct on (record.payload ->> 'numeroControlePNCP')
      record.payload
    from raw.raw_records as record
    where record.record_type = 'pncp_contratacao'
      and record.payload ->> 'numeroControlePNCP' is not null
    order by record.payload ->> 'numeroControlePNCP', record.created_at desc
  ), options as (
    select
      'modalidade'::text as option_type,
      payload ->> 'modalidadeNome' as option_value
    from latest_contracts
    union all
    select
      'situacao'::text,
      payload ->> 'situacaoCompraNome'
    from latest_contracts
    union all
    select
      'orgao'::text,
      payload #>> '{unidadeOrgao,nomeUnidade}'
    from latest_contracts
  )
  select
    option_type,
    option_value,
    count(*)::bigint as procurement_count
  from options
  where option_value is not null and length(trim(option_value)) > 0
  group by option_type, option_value
  order by option_type, lower(option_value), option_value;
$function$;

revoke all on function api.get_pncp_procurement_filter_options() from public;
grant execute on function api.get_pncp_procurement_filter_options() to anon, authenticated;

comment on function api.get_pncp_procurement_filter_options() is
  'Opções de modalidade, situação e órgão observadas nas contratações PNCP preservadas.';
