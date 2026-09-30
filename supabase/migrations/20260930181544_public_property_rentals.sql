begin;

-- Aluguéis de imóveis pagos pela Prefeitura, pela classificação oficial do
-- próprio empenho (subelemento "LOCAÇÃO DE IMÓVEIS" no sistema WebRun). Cada
-- linha agrupa locador, órgão e contrato citado no histórico; a descrição é o
-- histórico literal do empenho mais recente (endereço e uso do imóvel), com
-- CPF mascarado. Valores somados em numeric, a partir do texto da fonte:
-- empenhado (bruto) e pago ao locador pela chave oficial do empenho. Só a
-- grade mais recente de cada mês entra, para recoleta não contar em dobro.

create index raw_artifacts_commitment_grid_month_idx
  on raw.raw_artifacts (
    (metadata -> 'cursor' ->> 'month'),
    retrieved_at desc,
    id desc
  )
  where metadata ->> 'schema_name' = 'municipal-commitments-webrun-grid';

create index raw_records_municipal_property_rental_idx
  on raw.raw_records (raw_artifact_id)
  where record_type = 'municipal_commitment_webrun'
    and payload ->> 'field1135665' ~* '^LOCA[ÇC][ÃA]O DE IM[ÓO]VE(L|IS)$';

create function api.get_public_property_rentals(p_year integer)
returns table (
  landlord_name text,
  public_body text,
  contract_text text,
  commitments integer,
  committed_amount text,
  paid_amount text,
  first_commitment_date date,
  last_commitment_date date,
  description text,
  latest_commitment_key text,
  grid_artifact_sha256 text,
  year_landlords integer,
  year_commitments integer,
  year_committed_amount text,
  year_paid_amount text,
  year_grid_months integer,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if p_year is null or p_year < 2024 or p_year > 2100 then
    raise exception 'ano deve estar entre 2024 e 2100' using errcode = '22023';
  end if;

  return query
  with commitment_grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id,
      artifact.sha256,
      artifact.metadata -> 'cursor' ->> 'month' as grid_month
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-commitments-webrun-grid'
      and artifact.metadata -> 'cursor' ->> 'month' like p_year::text || '-%'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  payment_grids as materialized (
    select distinct on (artifact.metadata -> 'cursor' ->> 'month')
      artifact.id
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'municipal-payments-webrun-grid'
    order by
      artifact.metadata -> 'cursor' ->> 'month',
      artifact.retrieved_at desc,
      artifact.id desc
  ),
  rentals as materialized (
    select
      record.payload,
      grid.sha256,
      to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') as issue_date,
      replace(replace(record.payload ->> 'field1082412', '.', ''), ',', '.')::numeric
        as amount,
      upper(regexp_replace(substring(
        record.payload ->> 'field1144634'
        from '(?i)contrato\s*(?:de\s*)?n\s*[º°o.]*\s*([0-9]{1,5}\s*/\s*[0-9]{4})'
      ), '\s', '', 'g')) as contract_text
    from raw.raw_records as record
    join commitment_grids as grid on grid.id = record.raw_artifact_id
    where record.record_type = 'municipal_commitment_webrun'
      and record.payload ->> 'field1135665' ~* '^LOCA[ÇC][ÃA]O DE IM[ÓO]VE(L|IS)$'
      and record.payload ->> 'field1082407' ~ ('^[0-9]{2}/[0-9]{2}/' || p_year::text || '$')
      and record.payload ->> 'field1144631' ~ '^O-[0-9]+$'
      and record.payload ->> 'field1082412'
        ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$'
  ),
  paid as (
    select
      rental.payload ->> 'field1144631' as commitment_key,
      sum(replace(replace(payment.payload ->> 'field1082592', '.', ''), ',', '.')::numeric)
        as amount
    from rentals as rental
    join raw.raw_records as payment
      on payment.record_type = 'municipal_payment_webrun'
     and payment.payload ->> 'field1082596' = rental.payload ->> 'field1144631'
    join payment_grids as grid on grid.id = payment.raw_artifact_id
    where payment.payload ->> 'field1082592'
      ~ '^-?[0-9]{1,3}(\.[0-9]{3})*(,[0-9]{1,2})?$|^-?[0-9]+(,[0-9]{1,2})?$'
    group by 1
  ),
  grouped as (
    select
      rental.payload ->> 'field1144629' as landlord_name,
      rental.payload ->> 'field1082413' as public_body,
      rental.contract_text,
      count(*)::integer as commitments,
      sum(rental.amount) as committed,
      coalesce(sum(paid.amount), 0) as paid,
      min(rental.issue_date) as first_date,
      max(rental.issue_date) as last_date,
      (array_agg(rental.payload ->> 'field1144634'
        order by rental.issue_date desc, rental.payload ->> 'field1144631' desc))[1]
        as description,
      (array_agg(rental.payload ->> 'field1144631'
        order by rental.issue_date desc, rental.payload ->> 'field1144631' desc))[1]
        as latest_key,
      (array_agg(rental.sha256
        order by rental.issue_date desc, rental.payload ->> 'field1144631' desc))[1]
        as latest_sha256
    from rentals as rental
    left join paid on paid.commitment_key = rental.payload ->> 'field1144631'
    group by 1, 2, 3
  ),
  totals as (
    select
      count(distinct grouped.landlord_name)::integer as landlords,
      sum(grouped.commitments)::integer as commitments,
      sum(grouped.committed) as committed,
      sum(grouped.paid) as paid
    from grouped
  )
  select
    grouped.landlord_name,
    grouped.public_body,
    grouped.contract_text,
    grouped.commitments,
    to_char(grouped.committed, 'FM999999999990.00'),
    to_char(grouped.paid, 'FM999999999990.00'),
    grouped.first_date,
    grouped.last_date,
    left(editorial.mask_cpf_v1(grouped.description), 700),
    grouped.latest_key,
    grouped.latest_sha256,
    totals.landlords,
    totals.commitments,
    to_char(totals.committed, 'FM999999999990.00'),
    to_char(totals.paid, 'FM999999999990.00'),
    (select count(*)::integer from commitment_grids),
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'municipal-property-rentals/1.0.0'::text
  from grouped
  cross join totals
  order by grouped.committed desc, grouped.landlord_name, grouped.contract_text
  limit 500;
end;
$function$;

revoke all on function api.get_public_property_rentals(integer) from public;
grant execute on function api.get_public_property_rentals(integer)
  to anon, authenticated;

comment on function api.get_public_property_rentals(integer) is
  'Aluguéis de imóveis por locador/contrato no ano (subelemento oficial do empenho WebRun): empenhado e pago ao locador em numeric, histórico literal com CPF mascarado.';

commit;
