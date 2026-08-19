begin;

-- Estende a conferencia de fornecedores publicados aos cadastros CEPIM
-- (entidades sem fins lucrativos impedidas) e Acordos de Leniencia, com a
-- mesma chave e o mesmo corredor privado cgu/sancoes/. O CEAF fica fora por
-- definicao: e consulta por CPF de pessoa fisica, vedada pelo gate de dados
-- pessoais. Espelho literal do cadastro; nada afirma culpa.

update source.source_endpoints
set config = config || jsonb_build_object(
  'parser_version', 'cgu-sanctions/1.1.0',
  'registries', jsonb_build_array('ceis', 'cnep', 'cepim', 'leniencia'),
  'query_strategy',
    'codigoSancionado/cnpjSancionado_por_fornecedor_publicado',
  'ceaf_excluded_reason', 'consulta_por_cpf_pessoa_fisica_vedada'
)
where slug = 'sanctions-api'
  and data_source_id = (
    select id from source.data_sources
    where slug = 'cgu-portal-transparencia'
  );

create or replace function api.get_public_supplier_sanctions(
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
      and record.payload ->> 'registry'
        in ('ceis', 'cnep', 'cepim', 'leniencia')
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

comment on function api.get_public_supplier_sanctions(integer) is
  'Sancoes CEIS/CNEP/CEPIM/leniencia de fornecedores publicados, espelho literal do cadastro federal; pessoa fisica nunca exposta; nao afirma culpa.';

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
  'migration:extend-supplier-sanctions-registries',
  'source_endpoint.updated',
  'source.source_endpoints',
  endpoint.id,
  jsonb_build_object(
    'source_slug', source.slug,
    'endpoint_slug', endpoint.slug,
    'registries', endpoint.config -> 'registries',
    'parser_version', endpoint.config -> 'parser_version'
  ),
  jsonb_build_object(
    'raw_visibility', 'private',
    'natural_persons_materialized', false,
    'ceaf_excluded_reason', 'consulta_por_cpf_pessoa_fisica_vedada',
    'secret_values_persisted', false
  )
from source.source_endpoints as endpoint
join source.data_sources as source on source.id = endpoint.data_source_id
where source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'sanctions-api';

notify pgrst, 'reload schema';

commit;
