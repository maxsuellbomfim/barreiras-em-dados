begin;

-- ADR 0086. Liquidações do sistema WebRun, mesmo protocolo dos empenhos; cada
-- linha traz a CHAVE oficial do empenho liquidado. Registra só a rota de
-- aquisição, sem cobertura nem publicação.
insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
select s.id, 'webrun-liquidacoes', 'html',
  'https://portaldatransparencia.sudoesteinformatica.com.br/webrun5/navigate.do',
  'GET', 10, 120, true,
  jsonb_build_object(
    'raw_visibility', 'private',
    'form_id', 7907,
    'grid_component_id', 1089430,
    'session_flow', 'openform.do GET -> executeRule.do POST (período) -> navigate.do GET',
    'partition', 'month',
    'full_coverage_start', '2024-01-01',
    'commitment_key', 'CHAVE do empenho nos campos ocultos do botão de detalhe',
    'rate_limit_basis', 'conservative-local-policy',
    'automatic_publication', false
  )
from source.data_sources s
where s.slug = 'prefeitura-barreiras-despesas-webrun'
on conflict (data_source_id, slug) do nothing;

commit;
