begin;

-- ADR 0086. Registra a rota de aquisição dos empenhos individuais do sistema
-- WebRun por trás do portal municipal; não registra cobertura nem autoriza
-- publicação de valores.
insert into source.data_sources (
  slug, name, description, authority_level, is_official, homepage_url,
  documentation_url, metadata
) values (
  'prefeitura-barreiras-despesas-webrun',
  'Prefeitura de Barreiras — Despesas (sistema Sudoeste/WebRun)',
  'Empenhos individuais publicados pelo portal da transparência municipal por sistema de terceiro, sem API documentada.',
  'official', true,
  'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral',
  'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral',
  jsonb_build_object(
    'operator', 'Sudoeste Informática',
    'observed_at', '2026-09-23',
    'automatic_publication', false
  )
) on conflict (slug) do nothing;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
select s.id, 'webrun-empenhos', 'html',
  'https://portaldatransparencia.sudoesteinformatica.com.br/webrun5/navigate.do',
  'GET', 10, 120, true,
  jsonb_build_object(
    'raw_visibility', 'private',
    'form_id', 7901,
    'grid_component_id', 1082469,
    'session_flow', 'openform.do GET -> executeRule.do POST (período) -> navigate.do GET',
    'partition', 'month',
    'full_coverage_start', '2024-01-01',
    'coverage_note', 'Série histórica anterior a 2024 falha na fonte; esses meses terminam parciais.',
    'rate_limit_basis', 'conservative-local-policy',
    'automatic_publication', false
  )
from source.data_sources s
where s.slug = 'prefeitura-barreiras-despesas-webrun'
on conflict (data_source_id, slug) do nothing;

commit;
