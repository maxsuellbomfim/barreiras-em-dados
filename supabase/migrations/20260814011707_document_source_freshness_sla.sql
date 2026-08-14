begin;

alter table source.source_endpoints
  add column freshness_policy_kind text not null default 'manual',
  add column freshness_expected_hours integer,
  add column freshness_grace_hours integer not null default 0,
  add column freshness_policy_note text not null default
    'Sem prazo contínuo documentado; atualização sob demanda.',
  add column freshness_policy_version text not null default
    'source-freshness/1.0.0',
  add constraint source_endpoints_freshness_policy_kind_check check (
    freshness_policy_kind in ('scheduled', 'publication_driven', 'manual')
  ),
  add constraint source_endpoints_freshness_expected_hours_check check (
    freshness_expected_hours is null or freshness_expected_hours > 0
  ),
  add constraint source_endpoints_freshness_grace_hours_check check (
    freshness_grace_hours >= 0
  ),
  add constraint source_endpoints_freshness_policy_consistency_check check (
    (
      freshness_policy_kind = 'scheduled'
      and freshness_expected_hours is not null
    ) or (
      freshness_policy_kind <> 'scheduled'
      and freshness_expected_hours is null
    )
  ),
  add constraint source_endpoints_freshness_policy_note_check check (
    length(btrim(freshness_policy_note)) > 0
  ),
  add constraint source_endpoints_freshness_policy_version_check check (
    freshness_policy_version ~ '^source-freshness/[0-9]+\.[0-9]+\.[0-9]+$'
  );

-- Rotinas diárias. A tolerância adicional de 24 horas evita alarmes por uma
-- execução isolada perdida, mas acusa duas janelas consecutivas sem sucesso.
update source.source_endpoints as endpoint
set freshness_policy_kind = 'scheduled',
    freshness_expected_hours = 24,
    freshness_grace_hours = 24,
    freshness_policy_note =
      'Rotina diária; alerta após 48 horas sem atualização válida.',
    freshness_policy_version = 'source-freshness/1.0.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and (source.slug, endpoint.slug) in (
    ('barreiras-diario-oficial', 'catalogo-publicacoes'),
    ('barreiras-diario-oficial', 'pdf-direto'),
    ('pncp', 'compras-api'),
    ('pncp', 'consulta-contratacoes'),
    ('pncp', 'contratos-api'),
    ('prefeitura-barreiras-transparencia', 'dados-abertos-api'),
    ('querido-diario', 'gazettes-api'),
    ('transferegov-downloads', 'dados-abertos-catalogo'),
    ('transferegov-parcerias', 'distribuicoes-proposta'),
    ('transferegov-parcerias', 'documentos-habeis-parceria'),
    ('transferegov-parcerias', 'empenhos-parceria'),
    ('transferegov-parcerias', 'ordens-pagamento-documento'),
    ('transferegov-parcerias', 'parcerias-proposta'),
    ('transferegov-parcerias', 'propostas-barreiras')
  );

-- Rotinas semanais. As 48 horas de tolerância cobrem variações do provedor e
-- uma nova tentativa controlada sem esconder atraso persistente.
update source.source_endpoints as endpoint
set freshness_policy_kind = 'scheduled',
    freshness_expected_hours = 168,
    freshness_grace_hours = 48,
    freshness_policy_note =
      'Rotina semanal; alerta após nove dias sem atualização válida.',
    freshness_policy_version = 'source-freshness/1.0.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and (source.slug, endpoint.slug) in (
    ('alba', 'deputado-estadual-profile-html'),
    ('alba', 'deputados-estaduais-html'),
    ('camara-barreiras-transparencia', 'indicacoes-api'),
    ('camara-barreiras-transparencia', 'leis-api'),
    ('camara-federal', 'deputados-api'),
    ('camara-municipal-barreiras', 'vereadores-html'),
    ('pncp', 'registry-api'),
    ('prefeitura-barreiras', 'executive-pages-html')
  );

-- Essas fontes mudam por eleição, exercício orçamentário ou nova publicação
-- oficial. Idade do último retrato é mostrada, mas não vira atraso automático.
update source.source_endpoints as endpoint
set freshness_policy_kind = 'publication_driven',
    freshness_expected_hours = null,
    freshness_grace_hours = 0,
    freshness_policy_note =
      'Atualização orientada por nova publicação oficial; sem prazo contínuo.',
    freshness_policy_version = 'source-freshness/1.0.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and (
    source.slug in (
      'bahia-open-data',
      'bahia-seplan-budget',
      'tse'
    )
    or (
      source.slug = 'transferegov-downloads'
      and endpoint.slug in ('emendas-historicas', 'propostas-historicas')
    )
  );

create function api.get_collection_health_v3(
  page_size integer default 200
)
returns table (
  endpoint_id uuid,
  source_slug text,
  source_name text,
  source_status text,
  endpoint_slug text,
  endpoint_kind text,
  endpoint_enabled boolean,
  latest_partition_key text,
  latest_partition_status text,
  latest_period_start date,
  latest_period_end date,
  latest_expected_records integer,
  latest_observed_records integer,
  latest_attempted_at timestamptz,
  latest_completed_at timestamptz,
  latest_run_status text,
  latest_collector_version text,
  complete_partitions bigint,
  empty_partitions bigint,
  partial_partitions bigint,
  failed_partitions bigint,
  blocked_partitions bigint,
  unresolved_failures bigint,
  latest_failure_status text,
  latest_failure_type text,
  latest_failure_detail text,
  latest_failure_attempt_count integer,
  latest_failure_retryable boolean,
  latest_failure_next_retry_at timestamptz,
  latest_failure_at timestamptz,
  backfill_horizon date,
  continuous_coverage_start date,
  continuous_coverage_end date,
  next_backfill_start date,
  next_backfill_end date,
  backfill_classified_days integer,
  backfill_total_days integer,
  backfill_progress_percent double precision,
  latest_successful_partition_status text,
  latest_successful_period_start date,
  latest_successful_period_end date,
  latest_successful_observed_records integer,
  latest_successful_completed_at timestamptz,
  freshness_policy_kind text,
  freshness_expected_hours integer,
  freshness_grace_hours integer,
  freshness_policy_note text,
  freshness_due_at timestamptz,
  freshness_status text,
  freshness_overdue_hours integer,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  select
    health.endpoint_id,
    health.source_slug,
    health.source_name,
    health.source_status,
    health.endpoint_slug,
    health.endpoint_kind,
    health.endpoint_enabled,
    health.latest_partition_key,
    health.latest_partition_status,
    health.latest_period_start,
    health.latest_period_end,
    health.latest_expected_records,
    health.latest_observed_records,
    health.latest_attempted_at,
    health.latest_completed_at,
    health.latest_run_status,
    health.latest_collector_version,
    health.complete_partitions,
    health.empty_partitions,
    health.partial_partitions,
    health.failed_partitions,
    health.blocked_partitions,
    health.unresolved_failures,
    health.latest_failure_status,
    health.latest_failure_type,
    health.latest_failure_detail,
    health.latest_failure_attempt_count,
    health.latest_failure_retryable,
    health.latest_failure_next_retry_at,
    health.latest_failure_at,
    health.backfill_horizon,
    health.continuous_coverage_start,
    health.continuous_coverage_end,
    health.next_backfill_start,
    health.next_backfill_end,
    health.backfill_classified_days,
    health.backfill_total_days,
    health.backfill_progress_percent,
    health.latest_successful_partition_status,
    health.latest_successful_period_start,
    health.latest_successful_period_end,
    health.latest_successful_observed_records,
    health.latest_successful_completed_at,
    endpoint.freshness_policy_kind,
    endpoint.freshness_expected_hours,
    endpoint.freshness_grace_hours,
    endpoint.freshness_policy_note,
    case
      when endpoint.freshness_policy_kind = 'scheduled'
        and health.latest_successful_completed_at is not null
      then health.latest_successful_completed_at + make_interval(
        hours => endpoint.freshness_expected_hours
          + endpoint.freshness_grace_hours
      )
      else null
    end,
    case
      when endpoint.freshness_policy_kind <> 'scheduled'
        then 'not_monitored'
      when health.latest_successful_completed_at is null
        then 'never_updated'
      when statement_timestamp() >
        health.latest_successful_completed_at + make_interval(
          hours => endpoint.freshness_expected_hours
            + endpoint.freshness_grace_hours
        )
        then 'overdue'
      else 'current'
    end,
    case
      when endpoint.freshness_policy_kind = 'scheduled'
        and health.latest_successful_completed_at is not null
        and statement_timestamp() >
          health.latest_successful_completed_at + make_interval(
            hours => endpoint.freshness_expected_hours
              + endpoint.freshness_grace_hours
          )
      then floor(
        extract(epoch from (
          statement_timestamp()
          - health.latest_successful_completed_at
          - make_interval(
            hours => endpoint.freshness_expected_hours
              + endpoint.freshness_grace_hours
          )
        )) / 3600
      )::integer
      else 0
    end,
    'collection-health/1.3.0'::text
  from api.get_collection_health_v2(page_size) as health
  join source.source_endpoints as endpoint
    on endpoint.id = health.endpoint_id;
end;
$function$;

revoke all on function api.get_collection_health_v3(integer)
  from public, anon;
grant execute on function api.get_collection_health_v3(integer)
  to authenticated;

comment on function api.get_collection_health_v3(integer) is
  'Diagnóstico interno com prazo documentado e atraso baseado na última atualização válida, restrito a revisores ativos.';

comment on column source.source_endpoints.freshness_policy_kind is
  'scheduled aplica SLA contínuo; publication_driven e manual não geram atraso automático.';
comment on column source.source_endpoints.freshness_expected_hours is
  'Intervalo esperado entre atualizações válidas, sem a tolerância operacional.';

notify pgrst, 'reload schema';

commit;
