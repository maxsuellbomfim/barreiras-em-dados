-- Preserva ajustes negativos fora do grupo contábil de deduções.
-- Alguns demonstrativos registram estornos em códigos iniciados por 1.7;
-- rejeitar a linha inteira faria a série mensal desaparecer do portal.

alter table finance.revenues
  add column if not exists forecast_amount_signed numeric(20,2),
  add column if not exists collected_amount_signed numeric(20,2),
  add column if not exists accumulated_amount_signed numeric(20,2),
  drop constraint if exists revenues_collection_direction_check;

alter table finance.revenues
  add constraint revenues_collection_direction_check check (
    collection_direction in ('credit', 'deduction', 'adjustment')
  );

create or replace function api.get_public_revenues(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  revenue_id uuid,
  external_id text,
  fiscal_year smallint,
  revenue_date date,
  revenue_code text,
  description text,
  collected_amount numeric,
  accumulated_amount numeric,
  report_total_period_amount numeric,
  collection_direction text,
  currency text,
  public_body_name text,
  source_url text,
  document_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text,
  validation_status text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with ranked as (
    select
      revenue.*,
      row_number() over (
        partition by revenue.public_body_id,
          coalesce(revenue.external_id, revenue.id::text)
        order by revenue.version desc, revenue.created_at desc, revenue.id desc
      ) as current_row
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and (
        fiscal_year_filter is null
        or revenue.fiscal_year = fiscal_year_filter
      )
  )
  select
    revenue.id,
    revenue.external_id,
    revenue.fiscal_year,
    revenue.revenue_date,
    revenue.revenue_code,
    revenue.description,
    coalesce(
      revenue.collected_amount_signed,
      case
        when revenue.collection_direction in ('deduction', 'adjustment')
        then -revenue.collected_amount
        else revenue.collected_amount
      end
    ),
    coalesce(
      revenue.accumulated_amount_signed,
      case
        when revenue.collection_direction in ('deduction', 'adjustment')
        then -revenue.accumulated_amount
        else revenue.accumulated_amount
      end
    ),
    revenue.report_total_period_amount,
    revenue.collection_direction,
    revenue.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    'public-revenues/1.2.0',
    revenue.validation_status
  from ranked as revenue
  join org.public_bodies as body
    on body.id = revenue.public_body_id
  join raw.raw_records as origin
    on origin.id = revenue.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = revenue.source_document_artifact_id
   and document.artifact_kind = 'document'
  where revenue.current_row = 1
  order by revenue.revenue_date desc nulls last, revenue.created_at desc,
    revenue.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_revenues(integer, smallint) from public;
grant execute on function api.get_public_revenues(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_revenues(integer, smallint) is
  'Receitas validadas; ajustes negativos preservam sinal e nao sao deducoes do FUNDEB.';
