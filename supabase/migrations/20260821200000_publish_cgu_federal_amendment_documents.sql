begin;

-- Complementa o retrato agregado da CGU com os documentos anuais de
-- empenho, liquidacao e pagamento. A serie documental permanece separada:
-- seus valores nunca sao somados ao retrato agregado nem ao Transferegov.

insert into source.source_endpoints (
  data_source_id,
  slug,
  endpoint_kind,
  base_url,
  http_method,
  rate_limit_per_minute,
  request_timeout_seconds,
  enabled,
  config
)
values (
  (select id from source.data_sources where slug = 'cgu-portal-transparencia'),
  'federal-amendment-documents-open-data',
  'file',
  'https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares-documentos/{year}',
  'GET',
  2,
  180,
  true,
  jsonb_build_object(
    'parser_version', 'cgu-federal-amendment-documents/1.0.0',
    'archive_pattern', '{year}_EmendasParlamentaresPorDocumento.zip',
    'municipality_ibge_code', '2903201',
    'coverage_start_year', 2021,
    'raw_visibility', 'private',
    'aggregation_policy', 'single_document_source_no_cross_source_sum'
  )
)
on conflict (data_source_id, slug) do update
set
  endpoint_kind = excluded.endpoint_kind,
  base_url = excluded.base_url,
  http_method = excluded.http_method,
  rate_limit_per_minute = excluded.rate_limit_per_minute,
  request_timeout_seconds = excluded.request_timeout_seconds,
  enabled = excluded.enabled,
  config = excluded.config;

create view territory.latest_cgu_federal_amendment_document_archives as
with archive_years as (
  select
    artifact.id as raw_artifact_id,
    (record.payload ->> 'archive_year')::smallint as archive_year,
    artifact.retrieved_at,
    row_number() over (
      partition by (record.payload ->> 'archive_year')::smallint
      order by artifact.retrieved_at desc, artifact.id desc
    ) as archive_rank
  from raw.raw_artifacts as artifact
  join raw.raw_records as record
    on record.raw_artifact_id = artifact.id
  where record.record_type = 'cgu_federal_amendment_document'
    and record.payload ->> 'archive_year' ~ '^[0-9]{4}$'
  group by
    artifact.id,
    (record.payload ->> 'archive_year')::smallint,
    artifact.retrieved_at
)
select raw_artifact_id, archive_year, retrieved_at
from archive_years
where archive_rank = 1;

create view territory.cgu_federal_amendment_documents
with (security_barrier = true)
as
select
  record.id as raw_record_id,
  record.raw_artifact_id,
  (record.payload ->> 'archive_year')::smallint as archive_year,
  (record.payload ->> 'amendment_year')::smallint as amendment_year,
  btrim(record.payload ->> 'amendment_code') as amendment_code,
  btrim(record.payload ->> 'amendment_number') as amendment_number,
  btrim(record.payload ->> 'amendment_type') as amendment_type,
  case
    when lower(btrim(record.payload ->> 'amendment_type'))
      like 'emenda individual%' then 'person'
    when lower(btrim(record.payload ->> 'amendment_type'))
      like 'emenda de bancada%' then 'bench'
    when lower(btrim(record.payload ->> 'amendment_type'))
      like 'emenda de comiss%' then 'commission'
    else 'other'
  end as author_kind,
  btrim(record.payload ->> 'author_code') as author_code,
  btrim(record.payload ->> 'author_name') as author_name,
  lower(regexp_replace(
    btrim(record.payload ->> 'author_name'), '[[:space:]]+', ' ', 'g'
  )) as author_key,
  (record.payload ->> 'document_date')::date as document_date,
  btrim(record.payload ->> 'document_code') as document_code,
  btrim(record.payload ->> 'expense_stage') as expense_stage,
  btrim(record.payload ->> 'expense_stage_source') as expense_stage_source,
  (record.payload ->> 'committed_amount')::numeric(20,2) as committed_amount,
  (record.payload ->> 'paid_amount')::numeric(20,2) as paid_amount,
  btrim(record.payload ->> 'beneficiary_name') as beneficiary_name,
  btrim(record.payload ->> 'beneficiary_type') as beneficiary_type,
  btrim(record.payload ->> 'beneficiary_municipality')
    as beneficiary_municipality,
  btrim(record.payload ->> 'locality') as locality,
  btrim(record.payload ->> 'agency_name') as agency_name,
  btrim(record.payload ->> 'superior_agency_name') as superior_agency_name,
  btrim(record.payload ->> 'function_name') as function_name,
  btrim(record.payload ->> 'subfunction_name') as subfunction_name,
  btrim(record.payload ->> 'program_name') as program_name,
  btrim(record.payload ->> 'action_name') as action_name,
  btrim(record.payload ->> 'citizen_language') as citizen_language,
  btrim(record.payload ->> 'document_line_fingerprint')
    as document_line_fingerprint,
  (record.payload ->> 'source_row_number')::integer as source_row_number,
  artifact.source_url,
  artifact.sha256 as artifact_sha256,
  record.collected_at
from raw.raw_records as record
join territory.latest_cgu_federal_amendment_document_archives as latest
  on latest.raw_artifact_id = record.raw_artifact_id
join raw.raw_artifacts as artifact
  on artifact.id = record.raw_artifact_id
where record.record_type = 'cgu_federal_amendment_document'
  and record.payload ->> 'municipality_ibge' = '2903201'
  and record.payload ->> 'archive_year' ~ '^[0-9]{4}$'
  and record.payload ->> 'amendment_year' ~ '^[0-9]{4}$'
  and record.payload ->> 'document_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  and record.payload ->> 'expense_stage' in (
    'commitment', 'liquidation', 'payment'
  )
  and record.payload ->> 'committed_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and record.payload ->> 'paid_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and record.payload ->> 'document_line_fingerprint' ~ '^[0-9a-f]{64}$'
  and record.payload ->> 'source_row_number' ~ '^[1-9][0-9]*$'
  and nullif(btrim(record.payload ->> 'amendment_code'), '') is not null
  and nullif(btrim(record.payload ->> 'document_code'), '') is not null
  and nullif(btrim(record.payload ->> 'author_name'), '') is not null
  and artifact.source_url like 'https://%'
  and artifact.sha256 ~ '^[0-9a-f]{64}$';

revoke all on territory.latest_cgu_federal_amendment_document_archives
  from public, anon, authenticated;
revoke all on territory.cgu_federal_amendment_documents
  from public, anon, authenticated;

create function api.get_public_cgu_federal_amendment_documents(
  archive_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 200
)
returns table (
  archive_year smallint,
  amendment_year smallint,
  amendment_code text,
  amendment_number text,
  amendment_type text,
  author_kind text,
  author_key text,
  author_name text,
  document_date date,
  document_code text,
  expense_stage text,
  expense_stage_source text,
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  beneficiary_name text,
  beneficiary_type text,
  beneficiary_municipality text,
  locality text,
  agency_name text,
  superior_agency_name text,
  function_name text,
  subfunction_name text,
  program_name text,
  action_name text,
  citizen_language text,
  source_row_number integer,
  source_url text,
  artifact_sha256 text,
  collected_at timestamptz,
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
  if page_size is null or page_size < 1 or page_size > 500 then
    raise exception 'limite de documentos federais da CGU invalido'
      using errcode = '22023';
  end if;
  if archive_year_filter is not null
    and (archive_year_filter < 2021 or archive_year_filter > 2100)
  then
    raise exception 'ano documental federal da CGU invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null and length(normalized_author_key) > 200 then
    raise exception 'autor documental federal da CGU invalido'
      using errcode = '22023';
  end if;

  return query
  select
    document.archive_year,
    document.amendment_year,
    document.amendment_code,
    document.amendment_number,
    document.amendment_type,
    document.author_kind,
    document.author_key,
    document.author_name,
    document.document_date,
    document.document_code,
    document.expense_stage,
    document.expense_stage_source,
    document.committed_amount,
    document.paid_amount,
    document.beneficiary_name,
    document.beneficiary_type,
    document.beneficiary_municipality,
    document.locality,
    document.agency_name,
    document.superior_agency_name,
    document.function_name,
    document.subfunction_name,
    document.program_name,
    document.action_name,
    document.citizen_language,
    document.source_row_number,
    document.source_url,
    document.artifact_sha256,
    document.collected_at,
    'cgu-federal-amendment-documents/1.0.0'::text
  from territory.cgu_federal_amendment_documents as document
  where (
    archive_year_filter is null
    or document.archive_year = archive_year_filter
  )
    and (
      normalized_author_key is null
      or document.author_key = normalized_author_key
    )
  order by
    document.document_date desc,
    document.document_code,
    document.source_row_number
  limit page_size;
end;
$$;

create function api.get_public_cgu_federal_amendment_document_ranking(
  archive_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_kind text,
  author_key text,
  author_name text,
  amendment_count integer,
  document_count integer,
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  first_document_date date,
  last_document_date date,
  aggregation_policy text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite do ranking documental da CGU invalido'
      using errcode = '22023';
  end if;
  if archive_year_filter is not null
    and (archive_year_filter < 2021 or archive_year_filter > 2100)
  then
    raise exception 'ano do ranking documental da CGU invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      document.author_kind,
      document.author_key,
      (array_agg(
        document.author_name
        order by document.document_date desc, document.raw_record_id desc
      ))[1] as author_name,
      count(distinct document.amendment_code)::integer as amendment_count,
      count(distinct document.document_code)::integer as document_count,
      coalesce(sum(document.committed_amount) filter (
        where document.expense_stage = 'commitment'
      ), 0)::numeric(20,2) as committed_amount,
      coalesce(sum(document.paid_amount) filter (
        where document.expense_stage = 'payment'
      ), 0)::numeric(20,2) as paid_amount,
      min(document.document_date) as first_document_date,
      max(document.document_date) as last_document_date
    from territory.cgu_federal_amendment_documents as document
    where (
      archive_year_filter is null
      or document.archive_year = archive_year_filter
    )
    group by document.author_kind, document.author_key
  ), ranked as (
    select
      row_number() over (
        order by
          grouped.paid_amount desc,
          grouped.committed_amount desc,
          grouped.author_name
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.rank_position,
    ranked.author_kind,
    ranked.author_key,
    ranked.author_name,
    ranked.amendment_count,
    ranked.document_count,
    ranked.committed_amount,
    ranked.paid_amount,
    ranked.first_document_date,
    ranked.last_document_date,
    'single_document_source_no_cross_source_sum'::text,
    'cgu-federal-amendment-document-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

revoke all on function api.get_public_cgu_federal_amendment_documents(
  smallint, text, integer
) from public;
revoke all on function api.get_public_cgu_federal_amendment_document_ranking(
  smallint, integer
) from public;
grant execute on function api.get_public_cgu_federal_amendment_documents(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_cgu_federal_amendment_document_ranking(
  smallint, integer
) to anon, authenticated;

comment on view territory.cgu_federal_amendment_documents is
  'Documentos anuais da CGU territorializados pelo IBGE 2903201; a serie nao e somada a outras fontes.';
comment on function api.get_public_cgu_federal_amendment_document_ranking(
  smallint, integer
) is
  'Ranking documental por pagamentos e empenhos da propria serie; fases e fontes nao sao misturadas.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
select
  'administrator',
  'migration:publish-cgu-federal-amendment-documents',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'parser_version', endpoint.config -> 'parser_version'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'municipality_scope', '2903201',
    'financial_stages_kept_separate', true,
    'cross_source_amounts_merged', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'federal-amendment-documents-open-data';

notify pgrst, 'reload schema';

commit;
