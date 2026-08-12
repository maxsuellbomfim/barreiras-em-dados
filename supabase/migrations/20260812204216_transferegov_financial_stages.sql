-- Amplia o espelho bruto oficial do Transferegov sem confundir os estagios
-- financeiros. A publicacao normalizada permanece bloqueada ate que haja uma
-- projection deterministica e evidencias ligadas aos registros brutos.

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
values
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'empenhos-parceria',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/empenho-parceria',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_parent', 'validated_barreiras_partnership',
      'parser_version', 'transferegov-parcerias-page/1.1.0',
      'maximum_page_size', 200,
      'financial_semantics', 'commitment_is_not_payment'
    )
  ),
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'documentos-habeis-parceria',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/documento-habil',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_parent', 'validated_barreiras_partnership',
      'parser_version', 'transferegov-parcerias-page/1.1.0',
      'maximum_page_size', 200,
      'financial_semantics', 'payable_document_is_not_bank_payment'
    )
  ),
  (
    (select id from source.data_sources where slug = 'transferegov-parcerias'),
    'ordens-pagamento-documento',
    'api',
    'https://api-publica.transferegov.gestao.gov.br/parcerias/ordem-pagamento',
    'GET',
    30,
    60,
    true,
    jsonb_build_object(
      'required_parent', 'validated_payable_document',
      'parser_version', 'transferegov-parcerias-page/1.1.0',
      'maximum_page_size', 200,
      'financial_semantics', 'payment_order_and_bank_order_are_distinct_facts',
      'bank_order_fields', jsonb_build_array(
        'nr_ordem_bancaria',
        'dt_emissao_ordem_bancaria'
      )
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
  'migration:transferegov-financial-stages',
  'source_endpoints.financial_chain_registered',
  'source.data_sources',
  source.id,
  jsonb_build_object(
    'endpoints', jsonb_build_array(
      'empenhos-parceria',
      'documentos-habeis-parceria',
      'ordens-pagamento-documento'
    )
  ),
  jsonb_build_object(
    'source', 'official-transferegov-openapi',
    'publication', 'raw_only_until_normalization'
  )
from source.data_sources as source
where source.slug = 'transferegov-parcerias';
