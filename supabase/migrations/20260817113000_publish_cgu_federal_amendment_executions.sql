begin;

-- Projeta a execucao federal de emendas regionalizada para Barreiras (CGU,
-- ADR 0069). O ZIP nacional permanece privado; apenas as linhas do IBGE
-- 2903201 viram serie publica. Estagios financeiros nunca sao somados entre
-- si: o unico total derivado permitido e pago no exercicio + restos pagos.
-- O vinculo com o Transferegov e por codigo oficial (ano + numero de emenda)
-- e serve para rotular sobreposicao, nunca para fundir valores.

-- 1) Registro da fonte e do endpoint. O coletor resolve (source_code,
--    endpoint_code) por slug no banco; sem este registro a coleta agendada
--    falha antes de baixar o arquivo.
insert into source.data_sources (
  id,
  slug,
  name,
  description,
  authority_level,
  is_official,
  homepage_url,
  documentation_url,
  status
)
values (
  '7d1f5a92-64c8-4b3a-9f0e-2b8a51c3d604',
  'cgu-portal-transparencia',
  'Portal da Transparência (CGU)',
  'Dados abertos do Governo Federal, incluindo o arquivo nacional de execução de emendas parlamentares.',
  'official',
  true,
  'https://portaldatransparencia.gov.br/',
  'https://portaldatransparencia.gov.br/dicionario-de-dados/emendas-parlamentares',
  'active'
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  documentation_url = excluded.documentation_url,
  status = excluded.status;

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
  'federal-amendments-open-data',
  'file',
  'https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO',
  'GET',
  2,
  180,
  true,
  jsonb_build_object(
    'parser_version', 'cgu-federal-amendments/1.0.0',
    'archive_name', 'EmendasParlamentares.zip',
    'archive_member', 'EmendasParlamentares.csv',
    'municipality_ibge_code', '2903201',
    'raw_visibility', 'private',
    'coverage_note',
      'ZIP nacional integral preservado; apenas linhas de Barreiras sao materializadas.'
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

-- 2) Ultimo retrato de cada linha materializada (replay idempotente).
create view territory.latest_cgu_federal_amendment_executions as
select distinct on (record.source_record_key)
  record.id as raw_record_id,
  record.raw_artifact_id,
  record.source_record_key,
  record.payload,
  record.payload_sha256,
  record.collected_at
from raw.raw_records as record
where record.record_type = 'cgu_federal_amendment_execution'
  and record.source_record_key is not null
order by record.source_record_key, record.collected_at desc, record.id desc;

-- 3) Projecao tipada com guardas deterministicas. A fonte publica
--    'Sem informação'/'S/I' quando nao identifica codigo ou autor; essas
--    linhas permanecem visiveis, mas nunca entram em ranking nominal.
create view territory.cgu_federal_amendment_executions
with (security_barrier = true)
as
select
  latest.raw_record_id,
  latest.raw_artifact_id,
  (latest.payload ->> 'fiscal_year')::smallint as fiscal_year,
  btrim(latest.payload ->> 'amendment_code') as amendment_code,
  btrim(latest.payload ->> 'amendment_code') ~ '^[0-9]{12}$'
    as has_official_code,
  btrim(latest.payload ->> 'amendment_number') as amendment_number,
  btrim(latest.payload ->> 'amendment_type') as amendment_type,
  case
    when lower(btrim(latest.payload ->> 'amendment_type'))
      like 'emenda individual%' then 'person'
    when lower(btrim(latest.payload ->> 'amendment_type'))
      like 'emenda de bancada%' then 'bench'
    when lower(btrim(latest.payload ->> 'amendment_type'))
      like 'emenda de comiss%' then 'commission'
    else 'other'
  end as author_kind,
  btrim(latest.payload ->> 'author_code') as author_code,
  btrim(latest.payload ->> 'author_name') as author_name,
  lower(regexp_replace(
    btrim(latest.payload ->> 'author_name'), '[[:space:]]+', ' ', 'g'
  )) as author_key,
  (
    btrim(latest.payload ->> 'author_code') ~ '^[0-9]+$'
    and lower(btrim(latest.payload ->> 'author_name')) <> 'sem informação'
  ) as author_identified,
  btrim(latest.payload ->> 'locality') as locality,
  btrim(latest.payload ->> 'function_code') as function_code,
  btrim(latest.payload ->> 'function_name') as function_name,
  btrim(latest.payload ->> 'subfunction_code') as subfunction_code,
  btrim(latest.payload ->> 'subfunction_name') as subfunction_name,
  btrim(latest.payload ->> 'program_code') as program_code,
  btrim(latest.payload ->> 'program_name') as program_name,
  btrim(latest.payload ->> 'action_code') as action_code,
  btrim(latest.payload ->> 'action_name') as action_name,
  btrim(latest.payload ->> 'budget_plan_code') as budget_plan_code,
  btrim(latest.payload ->> 'budget_plan_name') as budget_plan_name,
  (latest.payload ->> 'committed_amount')::numeric(20,2) as committed_amount,
  (latest.payload ->> 'liquidated_amount')::numeric(20,2)
    as liquidated_amount,
  (latest.payload ->> 'paid_amount')::numeric(20,2) as paid_amount,
  (latest.payload ->> 'outstanding_registered_amount')::numeric(20,2)
    as outstanding_registered_amount,
  (latest.payload ->> 'outstanding_cancelled_amount')::numeric(20,2)
    as outstanding_cancelled_amount,
  (latest.payload ->> 'outstanding_paid_amount')::numeric(20,2)
    as outstanding_paid_amount,
  (
    (latest.payload ->> 'paid_amount')::numeric(20,2)
    + (latest.payload ->> 'outstanding_paid_amount')::numeric(20,2)
  )::numeric(20,2) as effective_paid_amount,
  (latest.payload ->> 'source_row_number')::integer as source_row_number,
  artifact.source_url,
  artifact.sha256 as artifact_sha256,
  latest.collected_at
from territory.latest_cgu_federal_amendment_executions as latest
join raw.raw_artifacts as artifact
  on artifact.id = latest.raw_artifact_id
where latest.payload ->> 'municipality_ibge' = '2903201'
  and latest.payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
  and (latest.payload ->> 'fiscal_year')::integer between 2000 and 2100
  and nullif(btrim(latest.payload ->> 'amendment_code'), '') is not null
  and nullif(btrim(latest.payload ->> 'amendment_type'), '') is not null
  and nullif(btrim(latest.payload ->> 'author_code'), '') is not null
  and nullif(btrim(latest.payload ->> 'author_name'), '') is not null
  and nullif(btrim(latest.payload ->> 'amendment_number'), '') is not null
  and latest.payload ->> 'committed_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'liquidated_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'paid_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'outstanding_registered_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'outstanding_cancelled_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'outstanding_paid_amount'
    ~ '^-?[0-9]+(?:[.][0-9]{1,2})?$'
  and latest.payload ->> 'source_row_number' ~ '^[1-9][0-9]*$'
  and artifact.source_url like 'https://%'
  and artifact.sha256 ~ '^[0-9a-f]{64}$';

-- 4) Vinculo por codigo oficial com a serie Transferegov ja reconciliada.
--    Rotula sobreposicao entre fontes; nenhuma fusao de valores acontece.
create view territory.cgu_transferegov_amendment_links
with (security_barrier = true)
as
with transferegov_codes as (
  select
    transfer.fiscal_year::text || lower(btrim(transfer.amendment_number))
      as official_code,
    count(*)::integer as transferegov_row_count,
    max(transfer.reconciliation_key) as transferegov_reconciliation_key
  from territory.reconciled_parliamentary_transfers as transfer
  where btrim(transfer.amendment_number) ~ '^[0-9]{8}$'
    and transfer.fiscal_year is not null
  group by 1
)
select
  execution.raw_record_id,
  execution.amendment_code,
  case
    when not execution.has_official_code then 'code_unavailable'
    when codes.official_code is null then 'not_found_in_transferegov'
    when codes.transferegov_row_count = 1 then 'matched_transferegov_unique'
    else 'conflict_non_unique_transferegov'
  end as transferegov_link_status,
  case
    when codes.transferegov_row_count = 1
      then codes.transferegov_reconciliation_key
  end as transferegov_reconciliation_key
from territory.cgu_federal_amendment_executions as execution
left join transferegov_codes as codes
  on execution.has_official_code
 and codes.official_code = execution.amendment_code;

revoke all on territory.latest_cgu_federal_amendment_executions from public;
revoke all on territory.latest_cgu_federal_amendment_executions
  from anon, authenticated;
revoke all on territory.cgu_federal_amendment_executions from public;
revoke all on territory.cgu_federal_amendment_executions
  from anon, authenticated;
revoke all on territory.cgu_transferegov_amendment_links from public;
revoke all on territory.cgu_transferegov_amendment_links
  from anon, authenticated;

-- 5) Listagem publica emenda por emenda, com evidencia e vinculo.
create function api.get_public_cgu_federal_amendment_executions(
  fiscal_year_filter smallint default null,
  author_key_filter text default null,
  page_size integer default 100
)
returns table (
  fiscal_year smallint,
  amendment_code text,
  has_official_code boolean,
  amendment_number text,
  amendment_type text,
  author_kind text,
  author_code text,
  author_key text,
  author_name text,
  author_identified boolean,
  locality text,
  function_code text,
  function_name text,
  subfunction_code text,
  subfunction_name text,
  program_code text,
  program_name text,
  action_code text,
  action_name text,
  budget_plan_code text,
  budget_plan_name text,
  committed_amount numeric(20,2),
  liquidated_amount numeric(20,2),
  paid_amount numeric(20,2),
  outstanding_registered_amount numeric(20,2),
  outstanding_cancelled_amount numeric(20,2),
  outstanding_paid_amount numeric(20,2),
  effective_paid_amount numeric(20,2),
  transferegov_link_status text,
  transferegov_reconciliation_key text,
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
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite de emendas federais da CGU invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2000 or fiscal_year_filter > 2100)
  then
    raise exception 'ano de emenda federal da CGU invalido'
      using errcode = '22023';
  end if;
  if normalized_author_key is not null
    and length(normalized_author_key) > 200
  then
    raise exception 'autor de emenda federal da CGU invalido'
      using errcode = '22023';
  end if;

  return query
  select
    execution.fiscal_year,
    execution.amendment_code,
    execution.has_official_code,
    execution.amendment_number,
    execution.amendment_type,
    execution.author_kind,
    execution.author_code,
    execution.author_key,
    execution.author_name,
    execution.author_identified,
    execution.locality,
    execution.function_code,
    execution.function_name,
    execution.subfunction_code,
    execution.subfunction_name,
    execution.program_code,
    execution.program_name,
    execution.action_code,
    execution.action_name,
    execution.budget_plan_code,
    execution.budget_plan_name,
    execution.committed_amount,
    execution.liquidated_amount,
    execution.paid_amount,
    execution.outstanding_registered_amount,
    execution.outstanding_cancelled_amount,
    execution.outstanding_paid_amount,
    execution.effective_paid_amount,
    link.transferegov_link_status,
    link.transferegov_reconciliation_key,
    execution.source_row_number,
    execution.source_url,
    execution.artifact_sha256,
    execution.collected_at,
    'cgu-federal-amendment-executions/1.0.0'::text
  from territory.cgu_federal_amendment_executions as execution
  join territory.cgu_transferegov_amendment_links as link
    on link.raw_record_id = execution.raw_record_id
  where (
    fiscal_year_filter is null
    or execution.fiscal_year = fiscal_year_filter
  )
    and (
      normalized_author_key is null
      or execution.author_key = normalized_author_key
    )
  order by
    execution.fiscal_year desc,
    execution.committed_amount desc,
    execution.author_name,
    execution.amendment_code,
    execution.source_row_number
  limit page_size;
end;
$$;

-- 6) Ranking deterministico da serie CGU. Ordena por valor empenhado e
--    exibe o pago efetivo (pago + restos pagos) sem misturar estagios.
--    Autoria nao identificada pela fonte nunca vira posicao nominal.
create function api.get_public_cgu_federal_amendment_ranking(
  author_scope text default 'person',
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_kind text,
  author_key text,
  author_name text,
  author_code text,
  amendment_count integer,
  committed_amount numeric(20,2),
  effective_paid_amount numeric(20,2),
  first_year smallint,
  last_year smallint,
  ranking_amount_stage text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  if author_scope not in ('person', 'collective') then
    raise exception 'author_scope deve ser person ou collective'
      using errcode = '22023';
  end if;
  if page_size is null or page_size < 1 or page_size > 200 then
    raise exception 'limite do ranking federal da CGU invalido'
      using errcode = '22023';
  end if;
  if fiscal_year_filter is not null
    and (fiscal_year_filter < 2000 or fiscal_year_filter > 2100)
  then
    raise exception 'ano do ranking federal da CGU invalido'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      execution.author_kind,
      execution.author_key,
      (array_agg(
        execution.author_name
        order by execution.fiscal_year desc, execution.raw_record_id desc
      ))[1] as author_name,
      (array_agg(
        execution.author_code
        order by execution.fiscal_year desc, execution.raw_record_id desc
      ))[1] as author_code,
      count(*)::integer as amendment_count,
      sum(execution.committed_amount)::numeric(20,2) as committed_amount,
      sum(execution.effective_paid_amount)::numeric(20,2)
        as effective_paid_amount,
      min(execution.fiscal_year)::smallint as first_year,
      max(execution.fiscal_year)::smallint as last_year
    from territory.cgu_federal_amendment_executions as execution
    where execution.author_identified
      and (
        fiscal_year_filter is null
        or execution.fiscal_year = fiscal_year_filter
      )
      and (
        (author_scope = 'person' and execution.author_kind = 'person')
        or (author_scope = 'collective' and execution.author_kind in (
          'commission', 'bench', 'collective'
        ))
      )
    group by execution.author_kind, execution.author_key
  ), ranked as (
    select
      row_number() over (
        order by
          grouped.committed_amount desc,
          grouped.effective_paid_amount desc,
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
    ranked.author_code,
    ranked.amendment_count,
    ranked.committed_amount,
    ranked.effective_paid_amount,
    ranked.first_year,
    ranked.last_year,
    'committed'::text,
    'cgu-federal-amendment-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$$;

revoke all on function api.get_public_cgu_federal_amendment_executions(
  smallint, text, integer
) from public;
revoke all on function api.get_public_cgu_federal_amendment_ranking(
  text, smallint, integer
) from public;

grant execute on function api.get_public_cgu_federal_amendment_executions(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_cgu_federal_amendment_ranking(
  text, smallint, integer
) to anon, authenticated;

comment on view territory.cgu_federal_amendment_executions is
  'Execucao federal de emendas regionalizada para Barreiras (CGU); municipio indica localizacao da execucao, nao repasse a Prefeitura.';
comment on view territory.cgu_transferegov_amendment_links is
  'Vinculo por codigo oficial entre a serie CGU e o Transferegov reconciliado; rotula sobreposicao sem fundir valores.';
comment on function api.get_public_cgu_federal_amendment_executions(
  smallint, text, integer
) is
  'Linhas oficiais da CGU para Barreiras com estagios financeiros separados, evidencia e vinculo com o Transferegov.';
comment on function api.get_public_cgu_federal_amendment_ranking(
  text, smallint, integer
) is
  'Ranking deterministico por valor empenhado da serie CGU; pago efetivo = pago no exercicio + restos pagos; sem autoria nao identificada.';

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
  'migration:publish-cgu-federal-amendment-executions',
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
    'effective_paid_definition', 'paid_amount + outstanding_paid_amount',
    'cross_source_amounts_merged', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'federal-amendments-open-data';

notify pgrst, 'reload schema';

commit;
