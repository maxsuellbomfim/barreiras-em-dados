begin;

-- municipal-property-rentals/1.3.0: endereço e uso do imóvel como TRECHOS
-- LITERAIS do histórico oficial do empenho (sem normalizar nem interpretar),
-- e quantos endereços distintos são citados no ano. Histórico sem endereço sai
-- como "não informado", nunca inventado.

-- Endereço: o que vem depois de "situado/localizado (à|na|no|em)" até o
-- primeiro marcador de fim (", com adequação", "para", "destinado", "CEP",
-- "na sede", "conforme"...). Ponto de abreviação (av., Pça., QD.) não corta.
create function finance.rental_address_v1(p_history text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select case when length(address) between 8 and 160 then address end
  from (
    select btrim(regexp_replace(
      substring(regexp_replace(coalesce(p_history, ''), '\s+', ' ', 'g')
        from '(?i)(?:situad[oa]|localizad[oa])\s+(?:(?:[àaá]s?|na|no|em)\s+)?(.*)$'),
      '(?i)\s*,?\s*(?:com adequa|para |pra |destinad|de propriedade|na sede|onde |cep\M|conforme|obedecendo|referente|(?<!\m(?:av|pça|pca|r|n|nº|qd|lt|dr|prof|profº|cel|des|sr|sra|edif|ed|lote|q))\.\s).*$',
      ''), ' ,.-') as address
  ) as extracted
$$;

-- Uso: o que vem depois de "funcionamento/atender/abrigar/sediar d(a|o)..."
-- até vírgula, ponto final, "na sede", "deste município"...
create function finance.rental_use_v1(p_history text)
returns text
language sql
immutable
parallel safe
set search_path = ''
as $$
  select case when length(use_text) between 3 and 160 then use_text end
  from (
    select btrim(regexp_replace(
      substring(regexp_replace(coalesce(p_history, ''), '\s+', ' ', 'g')
        from '(?i)(?:funcionamento|atender|abrigar|sediar(?:\s+as\s+instala[çc][õo]es)?)\s+(?:d[aoe]s?|[àa]s?|os?)\s+(.*)$'),
      '(?i)\s*(?:,|\.\s|\.(?=vig)|;|\s-\s|na sede|neste munic|deste munic|localizad|situad|obedecendo|conforme).*$',
      ''), ' ,.-') as use_text
  ) as extracted
$$;

revoke all on function finance.rental_address_v1(text) from public, anon;
revoke all on function finance.rental_use_v1(text) from public, anon;

drop function api.get_public_property_rentals(integer);

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
  address_text text,
  use_text text,
  latest_commitment_key text,
  grid_artifact_sha256 text,
  year_landlords integer,
  year_commitments integer,
  year_committed_amount text,
  year_paid_amount text,
  year_grid_months integer,
  year_addresses integer,
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
        from '(?i)contrato\s*(?:de\s*)?(?:n\s*[º°o.]*\s*)?([0-9]{1,5}(?:-?[a-z]{1,6})?\s*/\s*[0-9]{4})'
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
      editorial.mask_cpf_v1((array_agg(rental.payload ->> 'field1144634'
        order by rental.issue_date desc, rental.payload ->> 'field1144631' desc))[1])
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
  located as (
    select
      grouped.*,
      finance.rental_address_v1(grouped.description) as address,
      finance.rental_use_v1(grouped.description) as use_label
    from grouped
  ),
  totals as (
    select
      count(distinct lower(regexp_replace(grouped.address, '[^[:alnum:]]', '', 'g')))::integer
        as addresses,
      count(distinct grouped.landlord_name)::integer as landlords,
      sum(grouped.commitments)::integer as commitments,
      sum(grouped.committed) as committed,
      sum(grouped.paid) as paid
    from located as grouped
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
    left(grouped.description, 700),
    grouped.address,
    grouped.use_label,
    grouped.latest_key,
    grouped.latest_sha256,
    totals.landlords,
    totals.commitments,
    to_char(totals.committed, 'FM999999999990.00'),
    to_char(totals.paid, 'FM999999999990.00'),
    (select count(*)::integer from commitment_grids),
    totals.addresses,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'municipal-property-rentals/1.3.0'::text
  from located as grouped
  cross join totals
  order by grouped.committed desc, grouped.landlord_name, grouped.contract_text
  limit 500;
end;
$function$;

revoke all on function api.get_public_property_rentals(integer) from public;
grant execute on function api.get_public_property_rentals(integer)
  to anon, authenticated;

comment on function api.get_public_property_rentals(integer) is
  'Aluguéis de imóveis por locador/contrato no ano (subelemento oficial do empenho WebRun): empenhado e pago em numeric, histórico literal com CPF mascarado, endereço e uso como trechos literais do histórico.';

commit;
