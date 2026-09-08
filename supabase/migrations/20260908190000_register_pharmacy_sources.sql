begin;
insert into source.data_sources(slug,name,description,authority_level,is_official,homepage_url,metadata)
values('fns-farmacia-popular','Ministério da Saúde — Farmácia Popular',
  'Pagamentos FNS a estabelecimentos privados e cadastro institucional Infoms; não são receitas da Prefeitura.',
  'official',true,'https://consultafns.saude.gov.br/#/detalhada',
  '{"automatic_publication":false,"scope":"barreiras-private-pharmacy-pilot"}')
on conflict(slug) do nothing;
insert into source.source_endpoints(data_source_id,slug,endpoint_kind,base_url,http_method,
  rate_limit_per_minute,request_timeout_seconds,enabled,config)
select s.id,r.slug,r.kind,r.url,'GET',6,60,true,
  '{"raw_visibility":"private","automatic_publication":false,"collection_mode":"manual_pilot","municipality_ibge_code":"2903201"}'::jsonb
from source.data_sources s cross join(values
 ('payment','api','https://consultafns.saude.gov.br/recursos/consulta-detalhada/detalhe-pagamento'),
 ('register','file','https://infoms.saude.gov.br/extensions/SEIDIGI_DEMAS_PFPB_ENDERECOS/index.html')
) r(slug,kind,url) where s.slug='fns-farmacia-popular'
on conflict(data_source_id,slug) do nothing;
commit;
