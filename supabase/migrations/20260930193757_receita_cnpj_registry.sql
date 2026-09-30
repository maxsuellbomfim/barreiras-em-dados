begin;

-- ADR 0093. Cadastro oficial de CNPJ (dados abertos da Receita Federal) só
-- para os CNPJs que aparecem em contratos e licitações de Barreiras. O
-- coletor baixa os ZIPs mensais do compartilhamento público da Receita,
-- calcula o SHA-256 de cada um e preserva um extrato JSON com as linhas dos
-- CNPJs pedidos (sem telefone, e-mail ou endereço) no corredor privado
-- `receita/cnpj/`; cada CNPJ vira um `receita_cnpj_registry`.

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
        'receita/cnpj/',
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
  'receita-cnpj-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'receita/cnpj/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'receita_cnpj_registry_extract',
    'raw_visibility', 'private',
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

insert into source.data_sources (
  slug, name, description, authority_level, is_official, homepage_url,
  documentation_url, status, metadata
)
values (
  'receita-federal-cnpj',
  'Receita Federal - Dados abertos do CNPJ',
  'Cadastro Nacional da Pessoa Jurídica: razão social, nome fantasia, natureza jurídica e situação cadastral.',
  'official',
  true,
  'https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/dados-publicos-cnpj',
  'https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf',
  'active',
  jsonb_build_object('grain', 'cnpj', 'refresh', 'monthly', 'scope', 'contract_and_bid_suppliers')
)
on conflict (slug) do update
set
  name = excluded.name,
  description = excluded.description,
  authority_level = excluded.authority_level,
  is_official = excluded.is_official,
  homepage_url = excluded.homepage_url,
  documentation_url = excluded.documentation_url,
  status = excluded.status,
  metadata = excluded.metadata;

insert into source.source_endpoints (
  data_source_id, slug, endpoint_kind, base_url, http_method,
  rate_limit_per_minute, request_timeout_seconds, enabled, config
)
values (
  (select id from source.data_sources where slug = 'receita-federal-cnpj'),
  'dados-abertos-cnpj',
  'file',
  'https://arquivos.receitafederal.gov.br/public.php/webdav',
  'GET',
  10,
  120,
  true,
  jsonb_build_object(
    'collector_version', 'receita-cnpj-collector/1.0.0',
    'parser_version', 'receita-cnpj-extract/1.0.0',
    'files', 'Empresas0-9, Estabelecimentos0-9, Naturezas',
    'raw_visibility', 'private',
    'fields_excluded', 'telefone, e-mail, endereço, sócios'
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

-- CNPJs que o coletor deve procurar: contratados no portal municipal e
-- fornecedores de contratos e resultados do PNCP.
create function finance.get_cnpj_registry_targets()
returns table (cnpj text)
language sql
stable
security definer
set search_path = ''
as $$
  select distinct document.cnpj
  from (
    select regexp_replace(record.payload ->> 'documento', '[^0-9]', '', 'g') as cnpj
    from raw.raw_records as record
    where record.record_type = 'municipal_transparency_contratos'
    union all
    select regexp_replace(record.payload ->> 'niFornecedor', '[^0-9]', '', 'g')
    from raw.raw_records as record
    where record.record_type in ('pncp_contrato', 'pncp_resultado')
  ) as document
  where document.cnpj ~ '^[0-9]{14}$'
  order by 1
$$;

revoke all on function finance.get_cnpj_registry_targets()
  from public, anon, authenticated, service_role;
grant execute on function finance.get_cnpj_registry_targets() to collector_worker;

-- Cadastro vigente de cada CNPJ: a coleta mensal mais recente.
create function finance.cnpj_registry_latest()
returns table (
  cnpj text,
  razao_social text,
  nome_fantasia text,
  natureza_juridica text,
  natureza_juridica_descricao text,
  situacao_cadastral text,
  registry_month text,
  raw_record_id uuid
)
language sql
stable
security definer
set search_path = ''
as $$
  select distinct on (record.payload ->> 'cnpj')
    record.payload ->> 'cnpj',
    record.payload ->> 'razao_social',
    nullif(record.payload ->> 'nome_fantasia', ''),
    record.payload ->> 'natureza_juridica',
    record.payload ->> 'natureza_juridica_descricao',
    record.payload ->> 'situacao_cadastral',
    record.payload ->> 'registry_month',
    record.id
  from raw.raw_records as record
  where record.record_type = 'receita_cnpj_registry'
    and record.payload ->> 'cnpj' ~ '^[0-9]{14}$'
  order by record.payload ->> 'cnpj', record.payload ->> 'registry_month' desc,
    record.collected_at desc
$$;

revoke all on function finance.cnpj_registry_latest()
  from public, anon, authenticated, service_role;
grant execute on function finance.cnpj_registry_latest() to collector_worker;

commit;
