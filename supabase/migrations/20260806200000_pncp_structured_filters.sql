-- Filtros estruturados do PNCP. A projeção consulta somente registros brutos
-- preservados e não recalcula valores informados pela fonte oficial.

create function api.get_pncp_procurements_structured(
  page_size integer default 60,
  supplier_key_filter text default null,
  fiscal_year_filter smallint default null,
  query_filter text default null,
  modality_filter text default null,
  status_filter text default null,
  unit_filter text default null
)
returns table (
  control_number text,
  ano integer,
  sequencial integer,
  modalidade text,
  objeto text,
  situacao text,
  unidade text,
  valor_estimado numeric,
  valor_homologado numeric,
  data_publicacao date,
  resultados jsonb,
  methodology_version text
)
language plpgsql
stable
security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;
  if supplier_key_filter is not null and length(trim(supplier_key_filter)) > 200 then
    raise exception 'supplier_key_filter muito longo'
      using errcode = '22023';
  end if;
  if query_filter is not null and length(trim(query_filter)) > 120 then
    raise exception 'query_filter muito longo'
      using errcode = '22023';
  end if;
  if modality_filter is not null and length(trim(modality_filter)) > 120 then
    raise exception 'modality_filter muito longo'
      using errcode = '22023';
  end if;
  if status_filter is not null and length(trim(status_filter)) > 120 then
    raise exception 'status_filter muito longo'
      using errcode = '22023';
  end if;
  if unit_filter is not null and length(trim(unit_filter)) > 160 then
    raise exception 'unit_filter muito longo'
      using errcode = '22023';
  end if;

  return query
  select
    contratacao.control_number,
    contratacao.ano,
    contratacao.sequencial,
    contratacao.modalidade,
    contratacao.objeto,
    contratacao.situacao,
    contratacao.unidade,
    contratacao.valor_estimado,
    contratacao.valor_homologado,
    contratacao.data_publicacao,
    coalesce(resultado.lista, '[]'::jsonb),
    'pncp-procurements/1.2.0'::text
  from (
    select distinct on (record.payload ->> 'numeroControlePNCP')
      record.payload ->> 'numeroControlePNCP' as control_number,
      (record.payload ->> 'anoCompra')::int as ano,
      (record.payload ->> 'sequencialCompra')::int as sequencial,
      record.payload ->> 'modalidadeNome' as modalidade,
      record.payload ->> 'objetoCompra' as objeto,
      record.payload ->> 'situacaoCompraNome' as situacao,
      record.payload #>> '{unidadeOrgao,nomeUnidade}' as unidade,
      case when record.payload ->> 'valorTotalEstimado' ~ '^-?[0-9]+(\.[0-9]+)?$'
        then (record.payload ->> 'valorTotalEstimado')::numeric end as valor_estimado,
      case when record.payload ->> 'valorTotalHomologado' ~ '^-?[0-9]+(\.[0-9]+)?$'
        then (record.payload ->> 'valorTotalHomologado')::numeric end as valor_homologado,
      case when record.payload ->> 'dataPublicacaoPncp' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        then left(record.payload ->> 'dataPublicacaoPncp', 10)::date end as data_publicacao
    from raw.raw_records as record
    where record.record_type = 'pncp_contratacao'
      and record.payload ->> 'anoCompra' ~ '^[0-9]+$'
      and record.payload ->> 'sequencialCompra' ~ '^[0-9]+$'
      and (fiscal_year_filter is null or (record.payload ->> 'anoCompra')::int = fiscal_year_filter)
      and (modality_filter is null or lower(trim(record.payload ->> 'modalidadeNome')) = lower(trim(modality_filter)))
      and (status_filter is null or lower(trim(record.payload ->> 'situacaoCompraNome')) = lower(trim(status_filter)))
      and (unit_filter is null or lower(trim(record.payload #>> '{unidadeOrgao,nomeUnidade}')) = lower(trim(unit_filter)))
      and (
        query_filter is null
        or record.payload ->> 'objetoCompra' ilike '%' || trim(query_filter) || '%'
        or record.payload #>> '{unidadeOrgao,nomeUnidade}' ilike '%' || trim(query_filter) || '%'
      )
      and (
        supplier_key_filter is null
        or exists (
          select 1
          from raw.raw_records as result
          where result.record_type = 'pncp_resultado'
            and result.payload ->> 'numeroControlePNCPCompra' = record.payload ->> 'numeroControlePNCP'
            and (
              result.payload ->> 'niFornecedor' = trim(supplier_key_filter)
              or lower(regexp_replace(result.payload ->> 'nomeRazaoSocialFornecedor', '[^[:alnum:]]', '', 'g'))
                 = lower(regexp_replace(trim(supplier_key_filter), '[^[:alnum:]]', '', 'g'))
            )
        )
      )
    order by record.payload ->> 'numeroControlePNCP', record.created_at desc
  ) as contratacao
  left join lateral (
    select jsonb_agg(entry.item order by entry.numero_item) as lista
    from (
      select distinct on (
        winner.payload ->> 'numeroItem', winner.payload ->> 'sequencialResultado'
      )
        (winner.payload ->> 'numeroItem')::bigint as numero_item,
        jsonb_build_object(
          'numero_item', (winner.payload ->> 'numeroItem')::bigint,
          'fornecedor', winner.payload ->> 'nomeRazaoSocialFornecedor',
          'tipo_pessoa', winner.payload ->> 'tipoPessoa',
          'ni_fornecedor', case when winner.payload ->> 'tipoPessoa' = 'PJ' then winner.payload ->> 'niFornecedor' end,
          'valor_total_homologado', case when winner.payload ->> 'valorTotalHomologado' ~ '^-?[0-9]+(\.[0-9]+)?$' then (winner.payload ->> 'valorTotalHomologado')::numeric end,
          'data_resultado', case when winner.payload ->> 'dataResultado' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' then left(winner.payload ->> 'dataResultado', 10) end
        ) as item
      from raw.raw_records as winner
      where winner.record_type = 'pncp_resultado'
        and winner.payload ->> 'numeroControlePNCPCompra' = contratacao.control_number
        and winner.payload ->> 'numeroItem' ~ '^[0-9]+$'
      order by winner.payload ->> 'numeroItem', winner.payload ->> 'sequencialResultado', winner.created_at desc
    ) as entry
  ) as resultado on true
  order by contratacao.data_publicacao desc nulls last, contratacao.control_number
  limit page_size;
end;
$function$;

revoke all on function api.get_pncp_procurements_structured(integer, text, smallint, text, text, text, text) from public;
grant execute on function api.get_pncp_procurements_structured(integer, text, smallint, text, text, text, text)
  to anon, authenticated;

comment on function api.get_pncp_procurements_structured(integer, text, smallint, text, text, text, text) is
  'Contratações PNCP filtráveis por fornecedor, ano, objeto, modalidade, situação e unidade.';
