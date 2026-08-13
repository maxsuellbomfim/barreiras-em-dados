begin;

-- Projecao publica apenas das extracoes deterministicas validadas dos anexos
-- oficiais da LOA da Bahia. "Autorizado" e uma dotacao orcamentaria: esta
-- serie nao afirma empenho, transferencia, pagamento ou execucao do objeto.

create index if not exists extraction_results_bahia_state_loa_valid_idx
  on raw.extraction_results (created_at desc, id desc)
  where candidate_type = 'bahia_state_loa_authorized_amendment'
    and extractor_version = 'bahia-state-loa-barreiras/1.1.0'
    and validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and validation_status = 'valid';

create view territory.bahia_state_loa_amendments
with (security_barrier = true)
as
with eligible as (
  select
    result.id as origin_extraction_result_id,
    job.id as origin_extraction_job_id,
    artifact.id as origin_raw_artifact_id,
    result.result_payload as payload,
    result.created_at,
    row_number() over (
      partition by
        result.result_payload ->> 'source_artifact_sha256',
        result.result_payload ->> 'evidence_sha256'
      order by result.created_at desc, result.id desc
    ) as version_rank
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
   and job.status = 'succeeded'
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
   and artifact.sha256 = result.result_payload ->> 'source_artifact_sha256'
   and artifact.source_url = result.result_payload ->> 'source_url'
  where result.candidate_type = 'bahia_state_loa_authorized_amendment'
    and result.extractor_version = 'bahia-state-loa-barreiras/1.1.0'
    and result.validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and result.result_payload ->> 'financial_stage' = 'authorized'
    and lower(btrim(result.result_payload ->> 'municipality')) = 'barreiras'
    and result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
    and (result.result_payload ->> 'fiscal_year')::integer between 2022 and 2100
    and result.result_payload ->> 'authorized_amount'
      ~ '^[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    and (result.result_payload ->> 'authorized_amount')::numeric >= 0
    and nullif(btrim(result.result_payload ->> 'amendment_number'), '') is not null
    and nullif(btrim(result.result_payload ->> 'author_name'), '') is not null
    and nullif(btrim(result.result_payload ->> 'official_description'), '') is not null
    and nullif(btrim(result.result_payload ->> 'evidence_text'), '') is not null
    and result.result_payload ->> 'page_number' ~ '^[1-9][0-9]*$'
    and result.result_payload ->> 'source_url' like 'https://%'
    and result.result_payload ->> 'source_artifact_sha256' ~ '^[0-9a-f]{64}$'
    and result.result_payload ->> 'evidence_sha256' ~ '^[0-9a-f]{64}$'
)
select
  eligible.origin_extraction_result_id,
  eligible.origin_extraction_job_id,
  eligible.origin_raw_artifact_id,
  (eligible.payload ->> 'fiscal_year')::smallint as fiscal_year,
  btrim(eligible.payload ->> 'amendment_number') as amendment_number,
  nullif(btrim(eligible.payload ->> 'author_external_code'), '')
    as author_external_code,
  btrim(eligible.payload ->> 'author_name') as author_name,
  regexp_replace(
    regexp_replace(
      translate(
        lower(btrim(eligible.payload ->> 'author_name')),
        'áàãâäéèêëíìîïóòõôöúùûüç',
        'aaaaaeeeeiiiiooooouuuuc'
      ),
      '(^|[^[:alnum:]])jr[.]?([^[:alnum:]]|$)',
      '\1junior\2',
      'g'
    ),
    '[^[:alnum:]]+',
    ' ',
    'g'
  ) as author_key,
  (eligible.payload ->> 'authorized_amount')::numeric(20,2)
    as authorized_amount,
  btrim(eligible.payload ->> 'official_description') as official_description,
  nullif(btrim(eligible.payload ->> 'annex_code'), '') as annex_code,
  nullif(btrim(eligible.payload ->> 'budget_unit_code'), '')
    as budget_unit_code,
  nullif(btrim(eligible.payload ->> 'agency_code'), '') as agency_code,
  nullif(btrim(eligible.payload ->> 'action_code'), '') as action_code,
  (eligible.payload ->> 'page_number')::integer as page_number,
  btrim(eligible.payload ->> 'evidence_text') as evidence_text,
  'authorized'::text as financial_stage,
  eligible.payload ->> 'source_url' as source_url,
  eligible.payload ->> 'source_artifact_sha256' as source_artifact_sha256,
  eligible.payload ->> 'evidence_sha256' as evidence_sha256,
  eligible.created_at
from eligible
where eligible.version_rank = 1;

revoke all on territory.bahia_state_loa_amendments from public;
revoke all on territory.bahia_state_loa_amendments from anon, authenticated;

create function api.get_public_bahia_state_loa_amendments(
  fiscal_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 100
)
returns table (
  fiscal_year smallint,
  amendment_number text,
  author_external_code text,
  author_key text,
  author_name text,
  authorized_amount numeric(20,2),
  official_description text,
  annex_code text,
  budget_unit_code text,
  agency_code text,
  action_code text,
  page_number integer,
  evidence_text text,
  financial_stage text,
  source_url text,
  source_artifact_sha256 text,
  evidence_sha256 text,
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
  normalized_author_key text := nullif(btrim(author_key_filter), '');
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de emendas estaduais da LOA invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2022 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano de emenda estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null and length(normalized_author_key) > 200 then
    raise exception 'autor de emenda estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  select
    amendment.fiscal_year,
    amendment.amendment_number,
    amendment.author_external_code,
    amendment.author_key,
    amendment.author_name,
    amendment.authorized_amount,
    amendment.official_description,
    amendment.annex_code,
    amendment.budget_unit_code,
    amendment.agency_code,
    amendment.action_code,
    amendment.page_number,
    amendment.evidence_text,
    amendment.financial_stage,
    amendment.source_url,
    amendment.source_artifact_sha256,
    amendment.evidence_sha256,
    'bahia-state-loa-amendments/1.0.0'::text
  from territory.bahia_state_loa_amendments as amendment
  where (
    fiscal_year_filter is null
    or amendment.fiscal_year = fiscal_year_filter
  )
    and (
      normalized_author_key is null
      or amendment.author_key = normalized_author_key
    )
  order by
    amendment.fiscal_year desc,
    amendment.authorized_amount desc,
    amendment.author_name,
    amendment.amendment_number,
    amendment.page_number
  limit page_size;
end;
$$;

create function api.get_public_bahia_state_loa_amendment_ranking(
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_external_code text,
  amendment_count integer,
  authorized_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  financial_stage text,
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
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite do ranking estadual da LOA invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2022 or fiscal_year_filter > current_fiscal_year)
  then
    raise exception 'ano do ranking estadual da LOA invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      amendment.author_key,
      (array_agg(
        amendment.author_name
        order by amendment.fiscal_year desc, amendment.created_at desc
      ))[1] as author_name,
      (array_agg(
        amendment.author_external_code
        order by
          (amendment.author_external_code is not null) desc,
          amendment.fiscal_year desc,
          amendment.created_at desc
      ))[1] as author_external_code,
      count(*)::integer as amendment_count,
      sum(amendment.authorized_amount)::numeric(20,2) as authorized_amount,
      min(amendment.fiscal_year)::smallint as first_year,
      max(amendment.fiscal_year)::smallint as last_year
    from territory.bahia_state_loa_amendments as amendment
    where (
      fiscal_year_filter is null
      or amendment.fiscal_year = fiscal_year_filter
    )
    group by amendment.author_key
  ), ranked as (
    select
      row_number() over (
        order by grouped.authorized_amount desc, grouped.author_name
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_external_code,
    ranked.amendment_count,
    ranked.authorized_amount,
    ranked.first_year,
    ranked.last_year,
    'authorized'::text,
    'bahia-state-loa-amendment-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

revoke all on function api.get_public_bahia_state_loa_amendments(
  smallint, text, integer
) from public;
revoke all on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) from public;

grant execute on function api.get_public_bahia_state_loa_amendments(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) to anon, authenticated;

comment on view territory.bahia_state_loa_amendments is
  'Emendas para Barreiras autorizadas nos anexos oficiais da LOA da Bahia; nao comprova pagamento.';
comment on function api.get_public_bahia_state_loa_amendments(
  smallint, text, integer
) is
  'Emendas estaduais autorizadas, com autor, valor e evidencia oficial por linha.';
comment on function api.get_public_bahia_state_loa_amendment_ranking(
  smallint, integer
) is
  'Ranking deterministico por valor autorizado na LOA, sem nota subjetiva e sem afirmar execucao.';

notify pgrst, 'reload schema';

commit;
