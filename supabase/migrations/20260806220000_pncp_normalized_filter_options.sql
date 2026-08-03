-- Catálogo determinístico de opções PNCP. A chave agrupa caixa, espaços e
-- acentos sem substituir o texto original preservado.

create function api.get_pncp_procurement_filter_options_normalized()
returns table (
  option_type text,
  option_value text,
  variant_count bigint,
  variants jsonb,
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
  ), raw_options as (
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
  ), normalized_options as (
    select
      option_type,
      option_value,
      lower(
        regexp_replace(
          translate(
            trim(option_value),
            'ÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇáàãâäéèêëíìîïóòõôöúùûüç',
            'AAAAAEEEEIIIIOOOOOUUUUCAAAAAEEEEIIIIOOOOOUUUUC'
          ),
          '\s+',
          ' ',
          'g'
        )
      ) as normalized_key
    from raw_options
    where option_value is not null and length(trim(option_value)) > 0
  ), variant_counts as (
    select
      option_type,
      normalized_key,
      option_value,
      count(*)::bigint as procurement_count
    from normalized_options
    group by option_type, normalized_key, option_value
  )
  select
    option_type,
    min(option_value) as option_value,
    count(*)::bigint as variant_count,
    jsonb_agg(option_value order by option_value) as variants,
    sum(procurement_count)::bigint as procurement_count
  from variant_counts
  group by option_type, normalized_key
  order by option_type, lower(min(option_value)), min(option_value);
$function$;

revoke all on function api.get_pncp_procurement_filter_options_normalized() from public;
grant execute on function api.get_pncp_procurement_filter_options_normalized() to anon, authenticated;

comment on function api.get_pncp_procurement_filter_options_normalized() is
  'Catálogo PNCP agrupado determinísticamente por caixa, espaços e acentos, mantendo variantes originais.';
