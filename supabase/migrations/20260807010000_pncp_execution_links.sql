-- Exposicao publica somente de vinculos deterministas entre PNCP e execucao.
-- A chave oficial e procurement.external_id = numeroControlePNCP. Nenhum
-- vinculo por nome, valor ou proximidade textual e criado aqui.

create or replace function api.get_pncp_execution_summary(control_number_filter text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $function$
  with procurement_row as (
    select p.id
    from procurement.procurements as p
    where p.external_id = nullif(trim(control_number_filter), '')
    order by p.version desc, p.created_at desc, p.id desc
    limit 1
  ),
  current_contracts as (
    select c.id, c.current_amount
    from procurement.contracts as c
    join procurement_row as p on p.id = c.procurement_id
    where not exists (
      select 1
      from procurement.contracts as newer
      where newer.supersedes_id = c.id
    )
  ),
  current_commitments as (
    select c.id, c.amount, c.cancelled_amount
    from finance.commitments as c
    join procurement_row as p
      on c.procurement_id = p.id
      or c.contract_id in (select id from current_contracts)
    where not exists (
      select 1
      from finance.commitments as newer
      where newer.supersedes_id = c.id
    )
  ),
  current_liquidations as (
    select l.id, l.commitment_id, l.amount, l.cancelled_amount
    from finance.liquidations as l
    where l.commitment_id in (select id from current_commitments)
      and not exists (
        select 1
        from finance.liquidations as newer
        where newer.supersedes_id = l.id
      )
  ),
  current_payments as (
    select p.id, p.amount, p.reversed_amount
    from finance.payments as p
    where (
      p.commitment_id in (select id from current_commitments)
      or p.liquidation_id in (select id from current_liquidations)
    )
      and not exists (
        select 1
        from finance.payments as newer
        where newer.supersedes_id = p.id
      )
  ),
  totals as (
    select
      (select count(*)::integer from current_contracts) as contracts_count,
      (select count(*)::integer from current_commitments) as commitments_count,
      (select count(*)::integer from current_liquidations) as liquidations_count,
      (select count(*)::integer from current_payments) as payments_count,
      coalesce((select sum(current_amount) from current_contracts), 0)::numeric as contract_current_amount,
      coalesce((select sum(amount - cancelled_amount) from current_commitments), 0)::numeric as committed_amount,
      coalesce((select sum(amount - cancelled_amount) from current_liquidations), 0)::numeric as liquidated_amount,
      coalesce((select sum(amount - reversed_amount) from current_payments), 0)::numeric as paid_amount
  )
  select jsonb_build_object(
    'state', case
      when not exists (select 1 from procurement_row) then 'not_normalized'
      when totals.contracts_count + totals.commitments_count + totals.liquidations_count + totals.payments_count = 0
        then 'no_linked_execution'
      else 'linked'
    end,
    'methodology_version', 'pncp-execution-links/1.0.0',
    'contracts_count', totals.contracts_count,
    'commitments_count', totals.commitments_count,
    'liquidations_count', totals.liquidations_count,
    'payments_count', totals.payments_count,
    'contract_current_amount', totals.contract_current_amount,
    'committed_amount', totals.committed_amount,
    'liquidated_amount', totals.liquidated_amount,
    'paid_amount', totals.paid_amount
  )
  from totals;
$function$;

revoke all on function api.get_pncp_execution_summary(text) from public, anon, authenticated;

drop function if exists api.get_pncp_procurements_normalized(integer, text, smallint, text, text, text, text);

create function api.get_pncp_procurements_normalized(
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
  execution_summary jsonb,
  methodology_version text
)
language plpgsql
stable
security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  if fiscal_year_filter is not null and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido' using errcode = '22023';
  end if;
  if supplier_key_filter is not null and length(trim(supplier_key_filter)) > 200 then
    raise exception 'supplier_key_filter muito longo' using errcode = '22023';
  end if;
  if query_filter is not null and length(trim(query_filter)) > 120 then
    raise exception 'query_filter muito longo' using errcode = '22023';
  end if;
  if modality_filter is not null and length(trim(modality_filter)) > 120 then
    raise exception 'modality_filter muito longo' using errcode = '22023';
  end if;
  if status_filter is not null and length(trim(status_filter)) > 120 then
    raise exception 'status_filter muito longo' using errcode = '22023';
  end if;
  if unit_filter is not null and length(trim(unit_filter)) > 160 then
    raise exception 'unit_filter muito longo' using errcode = '22023';
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
    api.get_pncp_execution_summary(contratacao.control_number),
    'pncp-procurements/1.4.0'::text
  from (
    select distinct on (record.payload ->> 'numeroControlePNCP')
      record.payload ->> 'numeroControlePNCP' as control_number,
      (record.payload ->> 'anoCompra')::int as ano,
      (record.payload ->> 'sequencialCompra')::int as sequencial,
      record.payload ->> 'modalidadeNome' as modalidade,
      record.payload ->> 'objetoCompra' as objeto,
      record.payload ->> 'situacaoCompraNome' as situacao,
      record.payload #>> '{unidadeOrgao,nomeUnidade}' as unidade,
      case when record.payload ->> 'valorTotalEstimado' ~ '^-?[0-9]+(\\.[0-9]+)?$' then (record.payload ->> 'valorTotalEstimado')::numeric end as valor_estimado,
      case when record.payload ->> 'valorTotalHomologado' ~ '^-?[0-9]+(\\.[0-9]+)?$' then (record.payload ->> 'valorTotalHomologado')::numeric end as valor_homologado,
      case when record.payload ->> 'dataPublicacaoPncp' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' then left(record.payload ->> 'dataPublicacaoPncp', 10)::date end as data_publicacao
    from raw.raw_records as record
    where record.record_type = 'pncp_contratacao'
      and record.payload ->> 'anoCompra' ~ '^[0-9]+$'
      and record.payload ->> 'sequencialCompra' ~ '^[0-9]+$'
      and (fiscal_year_filter is null or (record.payload ->> 'anoCompra')::int = fiscal_year_filter)
      and (modality_filter is null or api.pncp_label_key(record.payload ->> 'modalidadeNome') = api.pncp_label_key(modality_filter))
      and (status_filter is null or api.pncp_label_key(record.payload ->> 'situacaoCompraNome') = api.pncp_label_key(status_filter))
      and (unit_filter is null or api.pncp_label_key(record.payload #>> '{unidadeOrgao,nomeUnidade}') = api.pncp_label_key(unit_filter))
      and (query_filter is null or record.payload ->> 'objetoCompra' ilike '%' || trim(query_filter) || '%' or record.payload #>> '{unidadeOrgao,nomeUnidade}' ilike '%' || trim(query_filter) || '%')
      and (
        supplier_key_filter is null
        or exists (
          select 1 from raw.raw_records as result
          where result.record_type = 'pncp_resultado'
            and result.payload ->> 'numeroControlePNCPCompra' = record.payload ->> 'numeroControlePNCP'
            and (result.payload ->> 'niFornecedor' = trim(supplier_key_filter) or lower(regexp_replace(result.payload ->> 'nomeRazaoSocialFornecedor', '[^[:alnum:]]', '', 'g')) = lower(regexp_replace(trim(supplier_key_filter), '[^[:alnum:]]', '', 'g')))
        )
      )
    order by record.payload ->> 'numeroControlePNCP', record.created_at desc
  ) as contratacao
  left join lateral (
    select jsonb_agg(entry.item order by entry.numero_item) as lista
    from (
      select distinct on (winner.payload ->> 'numeroItem', winner.payload ->> 'sequencialResultado')
        (winner.payload ->> 'numeroItem')::bigint as numero_item,
        jsonb_build_object(
          'numero_item', (winner.payload ->> 'numeroItem')::bigint,
          'fornecedor', winner.payload ->> 'nomeRazaoSocialFornecedor',
          'tipo_pessoa', winner.payload ->> 'tipoPessoa',
          'ni_fornecedor', case when winner.payload ->> 'tipoPessoa' = 'PJ' then winner.payload ->> 'niFornecedor' end,
          'valor_total_homologado', case when winner.payload ->> 'valorTotalHomologado' ~ '^-?[0-9]+(\\.[0-9]+)?$' then (winner.payload ->> 'valorTotalHomologado')::numeric end,
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

revoke all on function api.get_pncp_procurements_normalized(integer, text, smallint, text, text, text, text) from public;
grant execute on function api.get_pncp_procurements_normalized(integer, text, smallint, text, text, text, text) to anon, authenticated;

comment on function api.get_pncp_execution_summary(text) is
  'Resumo de vinculos PNCP para contratos, empenhos, liquidacoes e pagamentos por identificador oficial.';
comment on function api.get_pncp_procurements_normalized(integer, text, smallint, text, text, text, text) is
  'Contratacoes PNCP filtraveis com resumo de execucao financeira ligado somente por identificador oficial.';
