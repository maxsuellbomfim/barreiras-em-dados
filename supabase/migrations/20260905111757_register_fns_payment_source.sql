begin;

-- Operational pilot only. This registers acquisition routes, not collected
-- coverage, Storage permissions, review decisions or public financial values.
insert into source.data_sources (
  slug, name, description, authority_level, is_official, homepage_url, metadata
) values (
  'fns-consulta-detalhada',
  'Fundo Nacional de Saúde — Consulta Detalhada',
  'Evidência complementar de pagamentos Fundo a Fundo ao Fundo Municipal de Saúde de Barreiras; autor e solicitante permanecem separados.',
  'official', true, 'https://consultafns.saude.gov.br/#/detalhada',
  jsonb_build_object('scope', 'barreiras-faf-pilot', 'automatic_publication', false)
) on conflict (slug) do nothing;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
select s.id, route.slug, 'api',
  'https://consultafns.saude.gov.br/recursos/consulta-detalhada/' || route.path,
  'GET', 6, 60, true,
  jsonb_build_object(
    'raw_visibility', 'private',
    'municipality_ibge_code', '2903201',
    'fns_municipality_code', '290320',
    'beneficiary_cnpj', '08595187000125',
    'automatic_publication', false,
    'collection_mode', 'manual_pilot',
    'rate_limit_basis', 'conservative_local_policy_not_official_quota',
    'coverage_note', 'Cadastro de rota não comprova coleta. Originais bancários ficam privados; vínculo público exige revisão FNS/CGU.'
  )
from source.data_sources s
cross join (values
  ('payment-detail', 'detalhe-pagamento'),
  ('payment-order-detail', 'detalhe-ordem-bancaria')
) route(slug, path)
where s.slug = 'fns-consulta-detalhada'
on conflict (data_source_id, slug) do nothing;

commit;
