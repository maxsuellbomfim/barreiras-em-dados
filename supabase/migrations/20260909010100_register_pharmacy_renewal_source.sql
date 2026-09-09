begin;
insert into source.source_endpoints(data_source_id,slug,endpoint_kind,base_url,http_method,
  rate_limit_per_minute,request_timeout_seconds,enabled,config)
select s.id,'register-renewal','file',
  'https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/renovacao-de-estabelecimentos-participantes/empresas-credenciadas-para-realizar-a-renovacao-2025/@@download/file',
  'GET',6,60,true,
  '{"raw_visibility":"private","automatic_publication":false,"collection_mode":"manual_evidence","evidence_year":2025,"historical_accreditation":false}'::jsonb
from source.data_sources s where s.slug='fns-farmacia-popular'
on conflict(data_source_id,slug) do nothing;
commit;
