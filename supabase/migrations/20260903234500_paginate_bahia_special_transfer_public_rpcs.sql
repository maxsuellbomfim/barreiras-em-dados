begin;

create function api.get_public_bahia_special_transfer_payments(
  page_offset integer,
  fiscal_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 100
)
returns table (
  fiscal_year smallint,
  amendment_number text,
  amendment_year smallint,
  official_amendment_code text,
  source_author_name text,
  author_key text,
  official_author_name text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  association_status text,
  agency_name text,
  budget_unit_name text,
  action_name text,
  payment_id text,
  payment_number text,
  payment_date date,
  payment_amount numeric(20,2),
  payment_status text,
  object_text text,
  payment_url text,
  financial_stage text,
  territorial_scope text,
  federal_link_status text,
  aggregation_policy text,
  evidence_text text,
  evidence_sha256 text,
  source_url text,
  source_artifact_sha256 text,
  source_collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  normalized_author_key text := nullif(btrim(author_key_filter), '');
begin
  if page_offset is null or page_offset < 0 or page_offset > 1000000 then
    raise exception 'deslocamento da paginacao estadual invalido'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de pagamentos estaduais especiais invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2000 or fiscal_year_filter > 2100)
  then
    raise exception 'ano de pagamentos estaduais especiais invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null
    and length(normalized_author_key) > 200
  then
    raise exception 'autor de pagamentos estaduais especiais invalido'
      using errcode = '22023';
  end if;

  return query
  select
    payment.fiscal_year,
    payment.amendment_number,
    payment.amendment_year,
    payment.official_amendment_code,
    payment.source_author_name,
    payment.author_key,
    coalesce(payment.official_author_name, payment.source_author_name),
    payment.representative_source_kind,
    payment.representative_external_id,
    payment.representative_profile_url,
    payment.association_status,
    payment.agency_name,
    payment.budget_unit_name,
    payment.action_name,
    payment.payment_id,
    payment.payment_number,
    payment.payment_date,
    payment.payment_amount,
    payment.payment_status,
    payment.object_text,
    payment.payment_url,
    'paid_by_bahia_state'::text,
    payment.territorial_scope,
    federal.federal_link_status,
    'single_source_no_cross_source_sum'::text,
    payment.evidence_text,
    payment.evidence_sha256,
    payment.source_url,
    payment.source_artifact_sha256,
    payment.source_collected_at,
    'bahia-special-transfer-payments/1.0.0'::text
  from territory.bahia_special_transfer_payments as payment
  join territory.bahia_special_transfer_federal_links as federal
    on federal.extraction_result_id = payment.extraction_result_id
  where (
    fiscal_year_filter is null
    or payment.fiscal_year = fiscal_year_filter
  )
    and (
      normalized_author_key is null
      or payment.author_key = normalized_author_key
    )
  order by
    payment.payment_date desc,
    payment.payment_amount desc,
    payment.payment_id
  limit page_size
  offset page_offset;
end;
$$;

create function api.get_public_bahia_special_transfer_ranking(
  page_offset integer,
  fiscal_year_filter smallint default null,
  page_size integer default 10
)
returns table (
  rank_position integer,
  author_key text,
  official_author_name text,
  representative_source_kind text,
  representative_external_id text,
  representative_profile_url text,
  payment_count integer,
  amendment_count integer,
  paid_amount numeric(20,2),
  first_payment_date date,
  last_payment_date date,
  ranking_amount_stage text,
  territorial_scope text,
  aggregation_policy text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if page_offset is null or page_offset < 0 or page_offset > 1000000 then
    raise exception 'deslocamento da paginacao estadual invalido'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 50 then
    raise exception 'limite do ranking de pagamentos estaduais invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2000 or fiscal_year_filter > 2100)
  then
    raise exception 'ano do ranking de pagamentos estaduais invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      payment.author_key,
      max(payment.official_author_name) as official_author_name,
      max(payment.representative_source_kind) as representative_source_kind,
      max(payment.representative_external_id) as representative_external_id,
      max(payment.representative_profile_url) as representative_profile_url,
      count(*)::integer as payment_count,
      count(distinct payment.official_amendment_code)::integer
        as amendment_count,
      sum(payment.payment_amount)::numeric(20,2) as paid_amount,
      min(payment.payment_date) as first_payment_date,
      max(payment.payment_date) as last_payment_date
    from territory.bahia_special_transfer_payments as payment
    where payment.association_status =
        'approved_official_author_code_crosswalk'
      and (
        fiscal_year_filter is null
        or payment.fiscal_year = fiscal_year_filter
      )
    group by payment.author_key
  ), ranked as (
    select
      row_number() over (
        order by grouped.paid_amount desc, grouped.official_author_name,
          grouped.author_key
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.official_author_name,
    ranked.representative_source_kind,
    ranked.representative_external_id,
    ranked.representative_profile_url,
    ranked.payment_count,
    ranked.amendment_count,
    ranked.paid_amount,
    ranked.first_payment_date,
    ranked.last_payment_date,
    'paid_by_bahia_state'::text,
    'payment_object_literal_barreiras'::text,
    'single_source_no_cross_source_sum'::text,
    'bahia-special-transfer-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size
  offset page_offset;
end;
$$;

revoke all on function api.get_public_bahia_special_transfer_payments(
  integer, smallint, text, integer
) from public;
revoke all on function api.get_public_bahia_special_transfer_ranking(
  integer, smallint, integer
) from public;
grant execute on function api.get_public_bahia_special_transfer_payments(
  integer, smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_bahia_special_transfer_ranking(
  integer, smallint, integer
) to anon, authenticated;

comment on function api.get_public_bahia_special_transfer_payments(
  integer, smallint, text, integer
) is
  'Paginacao deterministica dos pagamentos estaduais territoriais, sem truncamento silencioso do acervo publico.';
comment on function api.get_public_bahia_special_transfer_ranking(
  integer, smallint, integer
) is
  'Paginacao deterministica do ranking estadual, preservando a posicao global calculada antes do deslocamento.';

notify pgrst, 'reload schema';

commit;
