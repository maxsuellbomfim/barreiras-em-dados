begin;

-- Projecao publica minima da cobertura anual do Transferegov. O RPC nao
-- devolve checkpoints, falhas, URLs internas nem detalhes de execucao.
create or replace function api.get_public_parliamentary_transfer_coverage(
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint
)
returns table (
  fiscal_year smallint,
  coverage_status text,
  proposal_count integer,
  published_amendment_count integer,
  last_attempted_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  current_fiscal_year smallint := extract(
    year from timezone('America/Sao_Paulo', statement_timestamp())
  )::smallint;
begin
  if fiscal_year_from is null
    or fiscal_year_to is null
    or fiscal_year_from < 2021
    or fiscal_year_from > fiscal_year_to
    or fiscal_year_to > current_fiscal_year
  then
    raise exception 'intervalo fiscal invalido para cobertura publica'
      using errcode = '22023';
  end if;

  return query
  with requested_years as (
    select year_value::smallint as fiscal_year
    from pg_catalog.generate_series(
      fiscal_year_from::integer,
      fiscal_year_to::integer
    ) as year_value
  ),
  endpoint as (
    select source_endpoint.id
    from source.source_endpoints as source_endpoint
    join source.data_sources as data_source
      on data_source.id = source_endpoint.data_source_id
    where data_source.slug = 'transferegov-parcerias'
      and source_endpoint.slug = 'propostas-barreiras'
    limit 1
  ),
  annual_partitions as (
    select
      requested.fiscal_year,
      partition.status,
      partition.checkpoint,
      partition.last_attempted_at
    from requested_years as requested
    cross join endpoint
    left join source.collection_partitions as partition
      on partition.source_endpoint_id = endpoint.id
      and partition.partition_key = (
        'fiscal-year:' || requested.fiscal_year::text
      )
  ),
  published as (
    select
      transfer.fiscal_year,
      count(*)::integer as amendment_count
    from territory.parliamentary_transfers as transfer
    where transfer.fiscal_year between fiscal_year_from and fiscal_year_to
    group by transfer.fiscal_year
  )
  select
    annual.fiscal_year,
    coalesce(annual.status, 'unclassified') as coverage_status,
    case
      when annual.status = 'empty' then 0
      when annual.status = 'complete'
        and annual.checkpoint ->> 'proposal_records' ~ '^[0-9]+$'
      then (annual.checkpoint ->> 'proposal_records')::integer
    end as proposal_count,
    case
      when annual.status in ('complete', 'empty')
      then coalesce(published.amendment_count, 0)
    end as published_amendment_count,
    annual.last_attempted_at,
    'parliamentary-transfer-coverage/1.0.0'::text as methodology_version
  from annual_partitions as annual
  left join published on published.fiscal_year = annual.fiscal_year
  order by annual.fiscal_year desc;
end;
$$;

revoke all on function api.get_public_parliamentary_transfer_coverage(
  smallint,
  smallint
) from public;
grant execute on function api.get_public_parliamentary_transfer_coverage(
  smallint,
  smallint
) to anon, authenticated;

comment on function api.get_public_parliamentary_transfer_coverage(
  smallint,
  smallint
) is
  'Cobertura anual sanitizada do Transferegov; vazio confirmado nao equivale a ausencia em outras fontes.';

notify pgrst, 'reload schema';

commit;
