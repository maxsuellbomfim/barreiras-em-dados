begin;

set local statement_timeout = '600s';

-- municipal-property-rentals/1.4.0: quando o histórico dos empenhos de um
-- locador nunca cita o endereço, ele é procurado no Diário Oficial (extratos
-- de contrato e de termo aditivo). O trecho lido começa no nome do locador e
-- para no próximo "EXTRATO", para não pegar o imóvel de outro contrato; só vale
-- quando todos os extratos encontrados dão o mesmo endereço. A busca varre o
-- texto das edições (~35 s), por isso fica numa tabela atualizada pelo worker.

create table finance.rental_gazette_addresses (
  landlord_name text primary key,
  address_text text not null,
  gazette_year integer not null,
  gazette_edition integer not null,
  page_number integer not null,
  document_page_id uuid not null references raw.document_pages(id),
  artifact_sha256 text not null check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  refreshed_at timestamptz not null
);

alter table finance.rental_gazette_addresses enable row level security;
revoke all on finance.rental_gazette_addresses from public, anon, authenticated;

create function finance.refresh_rental_gazette_addresses()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  refreshed integer;
begin
  perform pg_advisory_xact_lock(hashtext('finance.rental_gazette_addresses'));

  create temporary table rental_gazette_candidates on commit drop as
  with landlords as (
    select record.payload ->> 'field1144629' as landlord_name
    from raw.raw_records as record
    where record.record_type = 'municipal_commitment_webrun'
      and record.payload ->> 'field1135665' ~* '^LOCA[ÇC][ÃA]O DE IM[ÓO]VE(L|IS)$'
      and length(btrim(record.payload ->> 'field1144629')) >= 8
    group by 1
    having bool_and(finance.rental_address_v1(record.payload ->> 'field1144634') is null)
  ),
  pages as (
    select
      page.id,
      page.page_number,
      artifact.sha256,
      (artifact.metadata ->> 'year')::integer as gazette_year,
      (artifact.metadata ->> 'edition')::integer as gazette_edition,
      regexp_replace(page.text_content, '\s+', ' ', 'g') as page_text
    from raw.document_pages as page
    join raw.raw_artifacts as artifact on artifact.id = page.raw_artifact_id
    where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
      and artifact.metadata ->> 'year' ~ '^[0-9]{4}$'
      and artifact.metadata ->> 'edition' ~ '^[0-9]+$'
      and page.text_content ilike any (
        array(select '%' || landlords.landlord_name || '%' from landlords))
  ),
  windows as (
    select
      landlords.landlord_name,
      pages.*,
      regexp_replace(
        substr(pages.page_text, strpos(upper(pages.page_text), upper(landlords.landlord_name)), 900),
        '(?i)\mEXTRATO\M.*$', '') as excerpt
    from landlords
    join pages on strpos(upper(pages.page_text), upper(landlords.landlord_name)) > 0
  )
  select
    windows.landlord_name,
    finance.rental_address_v1(windows.excerpt) as address_text,
    windows.gazette_year,
    windows.gazette_edition,
    windows.page_number,
    windows.id as document_page_id,
    windows.sha256
  from windows
  where windows.excerpt ~* 'loca[çc][ãa]o'
    and finance.rental_address_v1(windows.excerpt) is not null;

  delete from finance.rental_gazette_addresses;
  insert into finance.rental_gazette_addresses
  select distinct on (candidate.landlord_name)
    candidate.landlord_name,
    candidate.address_text,
    candidate.gazette_year,
    candidate.gazette_edition,
    candidate.page_number,
    candidate.document_page_id,
    candidate.sha256,
    now()
  from rental_gazette_candidates as candidate
  where (
    select count(distinct lower(regexp_replace(other.address_text, '[^[:alnum:]]', '', 'g')))
    from rental_gazette_candidates as other
    where other.landlord_name = candidate.landlord_name
  ) = 1
  order by candidate.landlord_name, candidate.gazette_year desc,
    candidate.gazette_edition desc, candidate.page_number desc;
  get diagnostics refreshed = row_count;

  insert into audit.audit_events (
    actor_type, actor_subject, action, target_type, target_id, after_state, metadata
  ) values (
    'worker',
    'property-rentals',
    'source_snapshot.refreshed',
    'finance.rental_gazette_addresses',
    null,
    jsonb_build_object('row_count', refreshed),
    jsonb_build_object(
      'methodology_version', 'municipal-property-rentals/1.4.0',
      'records_deleted', false
    )
  );

  return refreshed;
end;
$function$;

revoke all on function finance.refresh_rental_gazette_addresses()
  from public, anon, authenticated, service_role;
grant execute on function finance.refresh_rental_gazette_addresses() to collector_worker;

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
  address_source text,
  address_gazette_year integer,
  address_gazette_edition integer,
  address_gazette_page integer,
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
  from_history as (
    select
      grouped.*,
      finance.rental_address_v1(grouped.description) as history_address,
      finance.rental_use_v1(grouped.description) as use_label
    from grouped
  ),
  -- 1.4.0: sem endereço no histórico do empenho, vale o extrato do Diário
  -- Oficial com o nome do locador (tabela atualizada pelo worker).
  located as (
    select
      from_history.*,
      coalesce(from_history.history_address, gazette.address_text) as address,
      case
        when from_history.history_address is not null then 'historico_empenho'
        when gazette.address_text is not null then 'diario_oficial'
      end as address_source,
      case when from_history.history_address is null then gazette.gazette_year end
        as gazette_year,
      case when from_history.history_address is null then gazette.gazette_edition end
        as gazette_edition,
      case when from_history.history_address is null then gazette.page_number end
        as gazette_page
    from from_history
    left join finance.rental_gazette_addresses as gazette
      on gazette.landlord_name = from_history.landlord_name
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
    grouped.address_source,
    grouped.gazette_year,
    grouped.gazette_edition,
    grouped.gazette_page,
    grouped.latest_key,
    grouped.latest_sha256,
    totals.landlords,
    totals.commitments,
    to_char(totals.committed, 'FM999999999990.00'),
    to_char(totals.paid, 'FM999999999990.00'),
    (select count(*)::integer from commitment_grids),
    totals.addresses,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'municipal-property-rentals/1.4.0'::text
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
  'Aluguéis de imóveis por locador/contrato no ano: empenhado e pago em numeric, histórico literal com CPF mascarado, endereço e uso literais do histórico ou, sem endereço no empenho, do extrato no Diário Oficial (edição e página).';

select finance.refresh_rental_gazette_addresses();

commit;
