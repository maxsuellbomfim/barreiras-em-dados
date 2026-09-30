begin;

-- ADR 0092. Dívida consolidada de Barreiras como a própria Prefeitura a
-- declara ao Tesouro no Relatório de Gestão Fiscal (RGF-Anexo 02, SICONFI).
-- O coletor preserva cada página JSON com SHA-256 e cada linha como
-- `siconfi_rgf_annex2_line`; a projeção devolve os valores literais da fonte,
-- por quadrimestre, sem nenhuma soma feita pela plataforma (ADR 0053).

alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'alba/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/',
        'municipal-transparency/',
        'prefeitura/executivo/',
        'transferegov/parcerias/',
        'bahia/emendas-estaduais/',
        'bahia/loa-emendas-estaduais/',
        'bahia/transferencias-especiais/',
        'cgu/emendas-federais/',
        'cgu/sancoes/',
        'siconfi/dca/',
        'siconfi/rgf/',
        'tcm-ba/monthly/',
        'tcm-ba/monthly-documents/',
        'fns/payments/'
      ]
    )
  );

insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix, can_select, can_insert,
  status, activated_at, metadata
)
values (
  'siconfi-rgf-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'siconfi/rgf/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'siconfi_rgf_annex2_raw_pages',
    'raw_visibility', 'private',
    'financial_grain', 'quadrimester_source_line',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do update
set
  slug = excluded.slug,
  can_select = excluded.can_select,
  can_insert = excluded.can_insert,
  status = excluded.status,
  activated_at = excluded.activated_at,
  metadata = excluded.metadata;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  (select id from source.data_sources where slug = 'siconfi-barreiras'),
  'rgf-anexo-02',
  'api',
  'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf',
  'GET',
  60,
  60,
  true,
  jsonb_build_object(
    'collector_version', 'siconfi-rgf-annex2-collector/1.0.0',
    'parser_version', 'siconfi-rgf-annex2-page/1.0.0',
    'municipality_ibge_code', '2903201',
    'coverage_year_from', 2019,
    'page_size', 5000,
    'grain', 'quadrimester_source_line',
    'annex', 'RGF-Anexo 02',
    'power', 'E',
    'raw_visibility', 'private',
    'public_projection', 'api.get_public_debt_statements'
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

insert into audit.audit_events (
  actor_type, actor_subject, action, target_type, target_id, after_state, metadata
)
select
  'administrator',
  'migration:register-siconfi-rgf-annex2',
  'source_endpoint.registered',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object('source_slug', source.slug, 'endpoint_slug', endpoint.slug),
  jsonb_build_object('raw_visibility', 'private', 'secret_values_persisted', false)
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'siconfi-barreiras'
  and endpoint.slug = 'rgf-anexo-02';

create function api.get_public_debt_statements()
returns table (
  fiscal_year integer,
  period integer,
  period_end date,
  consolidated_debt text,
  deductions text,
  net_consolidated_debt text,
  adjusted_net_current_revenue text,
  net_debt_revenue_percent text,
  senate_limit text,
  alert_limit text,
  composition jsonb,
  artifact_sha256 text,
  retrieved_at timestamptz,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
  with lines as materialized (
    select
      (record.payload ->> 'exercicio')::integer as fiscal_year,
      (record.payload ->> 'periodo')::integer as period,
      record.payload,
      record.record_index,
      artifact.id as artifact_id,
      artifact.sha256,
      artifact.retrieved_at
    from raw.raw_records as record
    join raw.raw_artifacts as artifact on artifact.id = record.raw_artifact_id
    where record.record_type = 'siconfi_rgf_annex2_line'
      and record.payload ->> 'anexo' = 'RGF-Anexo 02'
      and record.payload ->> 'co_poder' = 'E'
      and record.payload ->> 'exercicio' ~ '^[0-9]{4}$'
      and record.payload ->> 'periodo' in ('1', '2', '3')
  ),
  -- Retificação no SICONFI gera nova página: vale a coleta mais recente.
  latest as (
    select distinct on (lines.fiscal_year, lines.period)
      lines.fiscal_year, lines.period, lines.artifact_id, lines.sha256,
      lines.retrieved_at
    from lines
    order by lines.fiscal_year, lines.period, lines.retrieved_at desc,
      lines.artifact_id desc
  ),
  -- Só a coluna acumulada do próprio quadrimestre ("Até o 3º Quadrimestre").
  period_lines as (
    select lines.*
    from lines
    join latest
      on latest.artifact_id = lines.artifact_id
     and latest.fiscal_year = lines.fiscal_year
     and latest.period = lines.period
    where lines.payload ->> 'coluna' ~ ('^At[ée] o ' || lines.period::text || '[^0-9]')
  )
  select
    latest.fiscal_year,
    latest.period,
    (make_date(latest.fiscal_year, (array[4, 8, 12])[latest.period], 1)
      + interval '1 month - 1 day')::date,
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DividaConsolidada'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DeducoesDaDividaConsolidada'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'DividaConsolidadaLiquida'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta'
        = 'ReceitaCorrenteLiquidaAjustadaParaCalculoDosLimitesDeEndividamento'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'PercentualDaDCLSobreARCL'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'LimiteDefinidoPorResolucaoDoSenadoFederal'),
    max(line.payload ->> 'valor') filter (
      where line.payload ->> 'cod_conta' = 'LimiteDeAlerta'),
    coalesce(
      jsonb_agg(
        jsonb_build_object(
          'code', line.payload ->> 'cod_conta',
          'account', line.payload ->> 'conta',
          'value', line.payload ->> 'valor'
        )
        order by line.record_index
      ) filter (where line.payload is not null),
      '[]'::jsonb
    ),
    latest.sha256,
    latest.retrieved_at,
    'https://siconfi.tesouro.gov.br/siconfi/pages/public/consulta_finbra_rgf/finbra_rgf_list.jsf'::text,
    'municipal-debt-rgf-annex2/1.0.0'::text
  from latest
  left join period_lines as line
    on line.artifact_id = latest.artifact_id
   and line.fiscal_year = latest.fiscal_year
   and line.period = latest.period
  group by latest.fiscal_year, latest.period, latest.sha256, latest.retrieved_at
  order by latest.fiscal_year desc, latest.period desc;
$function$;

revoke all on function api.get_public_debt_statements() from public;
grant execute on function api.get_public_debt_statements() to anon, authenticated;

comment on function api.get_public_debt_statements() is
  'Dívida consolidada declarada por Barreiras no RGF-Anexo 02 (SICONFI), por quadrimestre: valores literais da fonte, composição completa e SHA-256 da página preservada (ADR 0092).';

commit;
