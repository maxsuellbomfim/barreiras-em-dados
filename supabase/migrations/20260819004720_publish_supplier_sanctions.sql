begin;

-- Sancoes federais (CEIS/CNEP) consultadas por CNPJ de fornecedor publicado.
-- Espelho literal do cadastro oficial da CGU: datas e fundamentacoes como
-- texto da fonte; nada e interpretado como culpa ou irregularidade — sancoes
-- podem estar sub judice. Pessoa fisica jamais e materializada nem publicada
-- (a API expoe CPF integral; o filtro por CNPJ e o gate duplo impedem).

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
  'sanctions-api',
  'api',
  'https://api.portaldatransparencia.gov.br/api-de-dados',
  'GET',
  50,
  60,
  true,
  jsonb_build_object(
    'parser_version', 'cgu-sanctions/1.0.0',
    'registries', jsonb_build_array('ceis', 'cnep'),
    'query_strategy', 'codigoSancionado_por_fornecedor_publicado',
    'auth', 'header chave-api-dados via secret TRANSPARENCIA_API_KEY',
    'raw_visibility', 'private',
    'natural_persons_materialized', false
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
        'cgu/emendas-federais/',
        'cgu/sancoes/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; inclui o pacote privado de sancoes CEIS/CNEP.';

insert into audit.storage_workload_identities (
  slug,
  auth_user_id,
  bucket_id,
  object_prefix,
  can_select,
  can_insert,
  status,
  activated_at,
  metadata
)
values (
  'cgu-sanctions-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'cgu/sancoes/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'cgu_sanction_raw_bundles',
    'workflow_identity', 'municipal-transparency',
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

create function api.get_public_supplier_sanctions(
  page_size integer default 100
)
returns table (
  sanction_record_id uuid,
  registry text,
  sanction_id text,
  supplier_cnpj text,
  sanctioned_name text,
  company_name text,
  sanction_type text,
  sanctioning_body text,
  sanctioning_body_sphere text,
  sanctioning_body_uf text,
  sanction_source text,
  process_number text,
  start_date_text text,
  end_date_text text,
  publication_date_text text,
  reference_date_text text,
  legal_basis_codes jsonb,
  api_source_url text,
  artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  with candidates as (
    select
      record.id,
      record.payload,
      record.created_at,
      artifact.source_url as api_source_url,
      artifact.sha256 as artifact_sha256,
      artifact.retrieved_at,
      row_number() over (
        partition by record.source_record_key
        order by record.created_at desc, record.id desc
      ) as current_row
    from raw.raw_records as record
    join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    where record.record_type = 'cgu_sanction'
      and record.payload ->> 'registry' in ('ceis', 'cnep')
      and record.payload ->> 'sanctioned_document' ~ '^[0-9]{14}$'
      and record.payload ->> 'supplier_cnpj' ~ '^[0-9]{14}$'
      and coalesce(record.payload ->> 'person_type', '')
        is distinct from 'Pessoa Física'
      and nullif(btrim(record.payload ->> 'sanctioned_name'), '') is not null
  )
  select
    candidate.id,
    candidate.payload ->> 'registry',
    candidate.payload ->> 'sanction_id',
    candidate.payload ->> 'supplier_cnpj',
    btrim(candidate.payload ->> 'sanctioned_name'),
    nullif(btrim(candidate.payload ->> 'company_name'), ''),
    nullif(btrim(candidate.payload ->> 'sanction_type'), ''),
    nullif(btrim(candidate.payload ->> 'sanctioning_body'), ''),
    nullif(btrim(candidate.payload ->> 'sanctioning_body_sphere'), ''),
    nullif(btrim(candidate.payload ->> 'sanctioning_body_uf'), ''),
    nullif(btrim(candidate.payload ->> 'sanction_source'), ''),
    nullif(btrim(candidate.payload ->> 'process_number'), ''),
    nullif(btrim(candidate.payload ->> 'start_date_text'), ''),
    nullif(btrim(candidate.payload ->> 'end_date_text'), ''),
    nullif(btrim(candidate.payload ->> 'publication_date_text'), ''),
    nullif(btrim(candidate.payload ->> 'reference_date_text'), ''),
    coalesce(candidate.payload -> 'legal_basis_codes', '[]'::jsonb),
    candidate.api_source_url,
    candidate.artifact_sha256,
    candidate.retrieved_at,
    'supplier-sanctions/1.0.0'::text
  from candidates as candidate
  where candidate.current_row = 1
  order by
    candidate.payload ->> 'supplier_cnpj',
    candidate.payload ->> 'registry',
    candidate.payload ->> 'sanction_id'
  limit page_size;
end;
$function$;

revoke all on function api.get_public_supplier_sanctions(integer) from public;
grant execute on function api.get_public_supplier_sanctions(integer)
  to anon, authenticated;

comment on function api.get_public_supplier_sanctions(integer) is
  'Sancoes CEIS/CNEP de fornecedores publicados, espelho literal do cadastro federal; pessoa fisica nunca exposta; nao afirma culpa.';

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
  'migration:publish-supplier-sanctions',
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
    'natural_persons_materialized', false,
    'query_strategy', 'codigoSancionado_por_fornecedor_publicado',
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'sanctions-api';

notify pgrst, 'reload schema';

commit;
