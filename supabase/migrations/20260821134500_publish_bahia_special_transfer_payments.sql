begin;

-- A autoria somente e associada quando um codigo oficial, um periodo de
-- mandato e um perfil institucional foram curados. Consultas publicas nunca
-- aproximam nomes.
create table political.parliamentary_author_code_crosswalk (
  source_system text not null check (
    source_system in ('federal_amendment_author_code')
  ),
  source_author_code text not null check (
    source_author_code ~ '^[0-9]{4}$'
  ),
  source_author_name text not null check (
    length(btrim(source_author_name)) between 2 and 200
  ),
  official_author_name text not null check (
    length(btrim(official_author_name)) between 2 and 200
  ),
  author_key text not null check (
    author_key = lower(btrim(author_key))
    and length(author_key) between 2 and 200
  ),
  representative_source_kind text not null check (
    representative_source_kind in ('federal', 'state')
  ),
  representative_external_id text not null check (
    length(btrim(representative_external_id)) between 1 and 100
  ),
  representative_profile_url text not null check (
    representative_profile_url ~ '^https://'
  ),
  source_author_evidence_url text not null check (
    source_author_evidence_url ~ '^https://'
  ),
  identity_evidence_url text not null check (
    identity_evidence_url ~ '^https://'
  ),
  identity_evidence_note text not null check (
    length(btrim(identity_evidence_note)) between 40 and 2000
  ),
  valid_from_year smallint not null check (
    valid_from_year between 2000 and 2100
  ),
  valid_to_year smallint not null check (
    valid_to_year between 2000 and 2100
  ),
  review_status text not null default 'approved' check (
    review_status in ('pending', 'approved', 'rejected')
  ),
  approved_at timestamptz,
  methodology_version text not null default
    'parliamentary-author-code-crosswalk/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  primary key (source_system, source_author_code, valid_from_year),
  check (valid_from_year <= valid_to_year),
  check (review_status <> 'approved' or approved_at is not null)
);

create index parliamentary_author_code_crosswalk_lookup_idx
  on political.parliamentary_author_code_crosswalk (
    source_system, source_author_code, valid_from_year, valid_to_year
  )
  where review_status = 'approved';

create trigger parliamentary_author_code_crosswalk_set_updated_at
before update on political.parliamentary_author_code_crosswalk
for each row execute function audit.set_updated_at();

alter table political.parliamentary_author_code_crosswalk
  enable row level security;
alter table political.parliamentary_author_code_crosswalk
  force row level security;
revoke all on political.parliamentary_author_code_crosswalk
  from public, anon, authenticated;

insert into political.parliamentary_author_code_crosswalk (
  source_system,
  source_author_code,
  source_author_name,
  official_author_name,
  author_key,
  representative_source_kind,
  representative_external_id,
  representative_profile_url,
  source_author_evidence_url,
  identity_evidence_url,
  identity_evidence_note,
  valid_from_year,
  valid_to_year,
  review_status,
  approved_at
)
values (
  'federal_amendment_author_code',
  '4072',
  'TITO',
  'Carlos Tito Marques Cordeiro',
  'tito',
  'federal',
  '197438',
  'https://www.camara.leg.br/deputados/197438',
  'https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=202340720005',
  'https://www.camara.leg.br/deputados/197438',
  'O Portal da Transparencia publica a emenda 202340720005 sob autoria TITO; '
    || 'o bloco 4072 e o mesmo codigo de autor presente nas emendas 40720003 '
    || 'e 40720005. O perfil oficial 197438 da Camara publica Tito como '
    || 'Carlos Tito Marques Cordeiro. O vinculo vale apenas para 2019-2023.',
  2019,
  2023,
  'approved',
  statement_timestamp()
);

-- Resultado validado mais recente por pagamento. O ZIP e os identificadores
-- do credor continuam privados; esta projecao nasce do payload ja minimizado.
create view territory.latest_bahia_special_transfer_payment_candidates
with (security_barrier = true)
as
select distinct on (typed.payment_id)
  typed.extraction_result_id,
  typed.raw_artifact_id,
  typed.fiscal_year,
  typed.amendment_number,
  typed.amendment_year,
  typed.source_author_name,
  typed.source_author_code,
  typed.official_amendment_code,
  typed.agency_name,
  typed.agency_code,
  typed.budget_unit_name,
  typed.budget_unit_code,
  typed.action_name,
  typed.expense_code,
  typed.execution_code,
  typed.payment_id,
  typed.payment_number,
  typed.payment_date,
  typed.payment_amount,
  typed.gcv_amount,
  typed.payment_status,
  typed.object_text,
  typed.payment_url,
  typed.territorial_scope,
  typed.evidence_text,
  typed.evidence_sha256,
  typed.source_url,
  typed.source_artifact_sha256,
  typed.source_collected_at,
  typed.result_created_at
from (
  select
    result.id as extraction_result_id,
    job.raw_artifact_id,
    case when result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
      then (result.result_payload ->> 'fiscal_year')::smallint
    end as fiscal_year,
    btrim(result.result_payload ->> 'amendment_number') as amendment_number,
    case when result.result_payload ->> 'amendment_year' ~ '^[0-9]{4}$'
      then (result.result_payload ->> 'amendment_year')::smallint
    end as amendment_year,
    btrim(result.result_payload ->> 'author_name') as source_author_name,
    case
      when btrim(result.result_payload ->> 'amendment_number') ~ '^[0-9]{8}$'
      then left(btrim(result.result_payload ->> 'amendment_number'), 4)
    end as source_author_code,
    case
      when result.result_payload ->> 'amendment_year' ~ '^[0-9]{4}$'
        and btrim(result.result_payload ->> 'amendment_number') ~ '^[0-9]{8}$'
      then (result.result_payload ->> 'amendment_year')
        || btrim(result.result_payload ->> 'amendment_number')
    end as official_amendment_code,
    btrim(result.result_payload ->> 'agency_name') as agency_name,
    btrim(result.result_payload ->> 'agency_code') as agency_code,
    btrim(result.result_payload ->> 'budget_unit_name') as budget_unit_name,
    btrim(result.result_payload ->> 'budget_unit_code') as budget_unit_code,
    btrim(result.result_payload ->> 'action_name') as action_name,
    btrim(result.result_payload ->> 'expense_code') as expense_code,
    btrim(result.result_payload ->> 'execution_code') as execution_code,
    btrim(result.result_payload ->> 'payment_id') as payment_id,
    btrim(result.result_payload ->> 'payment_number') as payment_number,
    case when result.result_payload ->> 'payment_date'
      ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then (result.result_payload ->> 'payment_date')::date
    end as payment_date,
    case when result.result_payload ->> 'payment_amount'
      ~ '^-?[0-9]+[.][0-9]{2}$'
      then (result.result_payload ->> 'payment_amount')::numeric(20,2)
    end as payment_amount,
    case
      when result.result_payload ->> 'gcv_amount' is null then null
      when result.result_payload ->> 'gcv_amount' ~ '^-?[0-9]+[.][0-9]{2}$'
      then (result.result_payload ->> 'gcv_amount')::numeric(20,2)
    end as gcv_amount,
    btrim(result.result_payload ->> 'payment_status') as payment_status,
    btrim(result.result_payload ->> 'object_text') as object_text,
    btrim(result.result_payload ->> 'payment_url') as payment_url,
    btrim(result.result_payload ->> 'territorial_scope') as territorial_scope,
    btrim(result.result_payload ->> 'evidence_text') as evidence_text,
    btrim(result.result_payload ->> 'evidence_sha256') as evidence_sha256,
    btrim(result.result_payload ->> 'source_url') as source_url,
    btrim(result.result_payload ->> 'source_artifact_sha256')
      as source_artifact_sha256,
    case when result.result_payload ->> 'source_collected_at' is not null
      then (result.result_payload ->> 'source_collected_at')::timestamptz
    end as source_collected_at,
    result.created_at as result_created_at
  from raw.extraction_results as result
  join raw.extraction_jobs as job on job.id = result.extraction_job_id
  where result.candidate_type =
      'bahia_special_transfer_payment_candidate'
    and result.extractor_version =
      'bahia-special-transfer-payment/1.0.0'
    and result.validator_version =
      'bahia-special-transfer-payment-validator/1.0.0'
    and result.validation_status = 'valid'
    and job.status = 'succeeded'
    and result.result_payload ->> 'schema_name' =
      'bahia-special-transfer-payment-candidate'
    and result.result_payload ->> 'schema_version' = '1.0.0'
) as typed
where typed.fiscal_year between 2000 and 2100
  and typed.amendment_year between 2000 and 2100
  and typed.amendment_number ~ '^[0-9]{8}$'
  and typed.payment_id ~ '^[0-9]{18,19}$'
  and typed.payment_date is not null
  and typed.payment_amount is not null
  and typed.source_author_name is not null
  and typed.source_author_name <> ''
  and typed.payment_status in ('Sim', 'Não', 'Em Processamento')
  and typed.object_text <> ''
  and typed.payment_url ~ '^https://www[.]transparencia[.]ba[.]gov[.]br/'
  and typed.territorial_scope = 'payment_object_literal_barreiras'
  and typed.evidence_sha256 ~ '^[0-9a-f]{64}$'
  and typed.source_url ~ '^https://'
  and typed.source_artifact_sha256 ~ '^[0-9a-f]{64}$'
  and typed.source_collected_at is not null
order by
  typed.payment_id,
  typed.source_collected_at desc,
  typed.result_created_at desc,
  typed.extraction_result_id desc;

create view territory.bahia_special_transfer_payments
with (security_barrier = true)
as
select
  payment.*,
  crosswalk.author_key,
  crosswalk.official_author_name,
  crosswalk.representative_source_kind,
  crosswalk.representative_external_id,
  crosswalk.representative_profile_url,
  case
    when crosswalk.source_author_code is not null
      then 'approved_official_author_code_crosswalk'
    else 'not_linked'
  end as association_status
from territory.latest_bahia_special_transfer_payment_candidates as payment
left join political.parliamentary_author_code_crosswalk as crosswalk
  on crosswalk.source_system = 'federal_amendment_author_code'
 and crosswalk.source_author_code = payment.source_author_code
 and payment.amendment_year between
   crosswalk.valid_from_year and crosswalk.valid_to_year
 and crosswalk.review_status = 'approved';

create view territory.bahia_special_transfer_federal_links
with (security_barrier = true)
as
with federal_codes as (
  select
    execution.amendment_code,
    count(*)::integer as execution_count
  from territory.cgu_federal_amendment_executions as execution
  where execution.has_official_code
  group by execution.amendment_code
)
select
  payment.extraction_result_id,
  payment.official_amendment_code,
  case
    when federal.execution_count is null then 'not_found_in_cgu'
    when federal.execution_count = 1 then 'matched_cgu_unique'
    else 'conflict_non_unique_cgu'
  end as federal_link_status,
  coalesce(federal.execution_count, 0) as federal_execution_count
from territory.bahia_special_transfer_payments as payment
left join federal_codes as federal
  on federal.amendment_code = payment.official_amendment_code;

revoke all on territory.latest_bahia_special_transfer_payment_candidates
  from public, anon, authenticated;
revoke all on territory.bahia_special_transfer_payments
  from public, anon, authenticated;
revoke all on territory.bahia_special_transfer_federal_links
  from public, anon, authenticated;

create function api.get_public_bahia_special_transfer_payments(
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
  limit page_size;
end;
$$;

create function api.get_public_bahia_special_transfer_ranking(
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
        order by grouped.paid_amount desc, grouped.official_author_name
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
  limit page_size;
end;
$$;

revoke all on function api.get_public_bahia_special_transfer_payments(
  smallint, text, integer
) from public;
revoke all on function api.get_public_bahia_special_transfer_ranking(
  smallint, integer
) from public;
grant execute on function api.get_public_bahia_special_transfer_payments(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_bahia_special_transfer_ranking(
  smallint, integer
) to anon, authenticated;

update source.source_endpoints as endpoint
set config = endpoint.config || jsonb_build_object(
  'normalization', 'published_with_deterministic_author_reconciliation',
  'public_projection', 'api.get_public_bahia_special_transfer_payments',
  'public_ranking', 'api.get_public_bahia_special_transfer_ranking',
  'financial_stage', 'paid_by_bahia_state',
  'municipal_receipt_proven', false,
  'physical_execution_proven', false,
  'cross_source_amounts_summed', false
)
from source.data_sources as source
where endpoint.data_source_id = source.id
  and source.slug = 'bahia-open-data'
  and endpoint.slug = 'state-special-transfers';

comment on table political.parliamentary_author_code_crosswalk is
  'Vinculos privados e curados entre codigos oficiais de autoria, periodo e perfis institucionais; sem aproximacao de nomes.';
comment on function api.get_public_bahia_special_transfer_payments(
  smallint, text, integer
) is
  'Pagamentos estaduais cujo objeto menciona Barreiras; nao comprova receita municipal nem execucao fisica e nao soma outras series.';
comment on function api.get_public_bahia_special_transfer_ranking(
  smallint, integer
) is
  'Ranking por pagamentos desta unica fonte estadual, somente para autorias oficialmente reconciliadas; nao soma CGU ou Transferegov.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:publish-bahia-special-transfer-payments',
  'methodology.bahia_special_transfer_payments_published',
  'api.get_public_bahia_special_transfer_payments',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'bahia-special-transfer-payments/1.0.0',
    'author_code', '4072',
    'representative_external_id', '197438',
    'source_endpoint_status',
      'published_with_deterministic_author_reconciliation'
  ),
  jsonb_build_object(
    'financial_stage', 'paid_by_bahia_state',
    'territorial_scope', 'payment_object_literal_barreiras',
    'municipal_receipt_proven', false,
    'physical_execution_proven', false,
    'cross_source_amounts_summed', false,
    'personal_identifiers_exposed', false
  )
);

notify pgrst, 'reload schema';

commit;
