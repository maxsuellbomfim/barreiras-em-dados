begin;

-- Prova que o conjunto normalizado usado pela projeção pública é o mesmo
-- observado na coleta anual atual. A API expõe somente contagem e impressão;
-- payloads, chaves individuais e identificadores internos continuam privados.
create function api.get_public_transferegov_current_snapshot_evidence()
returns table (
  fiscal_year smallint,
  coverage_status text,
  record_count integer,
  snapshot_fingerprint text,
  last_attempted_at timestamptz,
  source_url text,
  methodology_version text
)
language sql
stable
security definer
set search_path = ''
as $function$
with endpoint as (
  select source_endpoint.id, source_endpoint.base_url
  from source.source_endpoints as source_endpoint
  join source.data_sources as data_source
    on data_source.id = source_endpoint.data_source_id
  where data_source.slug = 'transferegov-parcerias'
    and source_endpoint.slug = 'propostas-barreiras'
), current_partitions as (
  select
    extract(year from partition.period_start)::smallint as fiscal_year,
    partition.status,
    partition.last_attempted_at
  from source.collection_partitions as partition
  join endpoint on endpoint.id = partition.source_endpoint_id
  where partition.partition_key =
    'fiscal-year:' || extract(year from partition.period_start)::integer::text
    and partition.status in ('complete', 'empty')
    and partition.period_start >= date '2021-01-01'
), latest_records as (
  select distinct on (record.record_type, record.source_record_key)
    record.record_type,
    record.source_record_key,
    record.payload_sha256,
    record.payload
  from raw.raw_records as record
  where record.record_type in (
    'transferegov_proposta',
    'transferegov_distribuicao_recurso',
    'transferegov_parceria',
    'transferegov_empenho',
    'transferegov_documento_habil',
    'transferegov_ordem_pagamento',
    'transferegov_ordem_bancaria'
  )
  order by
    record.record_type,
    record.source_record_key,
    record.collected_at desc,
    record.id desc
), proposals as (
  select
    (record.payload ->> 'ano_proposta')::smallint as fiscal_year,
    record.payload ->> 'id_proposta' as proposal_id,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  where record.record_type = 'transferegov_proposta'
    and record.payload ->> 'ano_proposta' ~ '^[0-9]{4}$'
    and record.payload ->> 'id_proposta' ~ '^[0-9]+$'
), distributions as (
  select
    proposal.fiscal_year,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  join proposals as proposal
    on proposal.proposal_id = record.payload ->> 'id_proposta'
  where record.record_type = 'transferegov_distribuicao_recurso'
), partnerships as (
  select
    proposal.fiscal_year,
    record.payload ->> 'id_parceria' as partnership_id,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  join proposals as proposal
    on proposal.proposal_id = record.payload ->> 'id_proposta'
  where record.record_type = 'transferegov_parceria'
    and record.payload ->> 'id_parceria' ~ '^[0-9]+$'
), commitments as (
  select
    partnership.fiscal_year,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  join partnerships as partnership
    on partnership.partnership_id = record.payload ->> 'id_parceria'
  where record.record_type = 'transferegov_empenho'
), payable_documents as (
  select
    partnership.fiscal_year,
    record.payload ->> 'id_documento_habil' as document_id,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  join partnerships as partnership
    on partnership.partnership_id = record.payload ->> 'id_parceria'
  where record.record_type = 'transferegov_documento_habil'
    and record.payload ->> 'id_documento_habil' ~ '^[0-9]+$'
), payment_records as (
  select
    document.fiscal_year,
    record.record_type,
    record.source_record_key,
    record.payload_sha256
  from latest_records as record
  join payable_documents as document
    on document.document_id = record.payload ->> 'id_documento_habil'
  where record.record_type in (
    'transferegov_ordem_pagamento',
    'transferegov_ordem_bancaria'
  )
), scoped_records as (
  select fiscal_year, record_type, source_record_key, payload_sha256
  from proposals
  union all
  select fiscal_year, record_type, source_record_key, payload_sha256
  from distributions
  union all
  select fiscal_year, record_type, source_record_key, payload_sha256
  from partnerships
  union all
  select fiscal_year, record_type, source_record_key, payload_sha256
  from commitments
  union all
  select fiscal_year, record_type, source_record_key, payload_sha256
  from payable_documents
  union all
  select fiscal_year, record_type, source_record_key, payload_sha256
  from payment_records
), manifests as (
  select
    record.fiscal_year,
    count(*)::integer as record_count,
    encode(
      pg_catalog.sha256(
        convert_to(
          string_agg(
            record.record_type || chr(31) ||
            coalesce(record.source_record_key, '<missing>') || chr(31) ||
            coalesce(record.payload_sha256, '<missing>'),
            E'\n'
            order by convert_to(
              record.record_type || chr(31) ||
              coalesce(record.source_record_key, '<missing>') || chr(31) ||
              coalesce(record.payload_sha256, '<missing>'),
              'UTF8'
            )
          ),
          'UTF8'
        )
      ),
      'hex'
    ) as snapshot_fingerprint
  from scoped_records as record
  group by record.fiscal_year
)
select
  partition.fiscal_year,
  partition.status::text as coverage_status,
  coalesce(manifest.record_count, 0)::integer as record_count,
  coalesce(
    manifest.snapshot_fingerprint,
    encode(pg_catalog.sha256(convert_to('', 'UTF8')), 'hex')
  )::text as snapshot_fingerprint,
  partition.last_attempted_at,
  endpoint.base_url as source_url,
  'transferegov-current-snapshot/1.0.0'::text as methodology_version
from current_partitions as partition
cross join endpoint
left join manifests as manifest
  on manifest.fiscal_year = partition.fiscal_year
order by partition.fiscal_year;
$function$;

revoke all on function
  api.get_public_transferegov_current_snapshot_evidence()
from public;
grant execute on function
  api.get_public_transferegov_current_snapshot_evidence()
to anon, authenticated;

comment on function
  api.get_public_transferegov_current_snapshot_evidence() is
  'Expõe contagem e SHA-256 do snapshot normalizado anual atual do Transferegov, sem payloads ou chaves individuais.';

insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  after_state,
  metadata
)
values (
  'administrator',
  'migration:publish-transferegov-snapshot-evidence',
  'methodology.transferegov_snapshot_evidence_published',
  'api.get_public_transferegov_current_snapshot_evidence',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'transferegov-current-snapshot/1.0.0',
    'fingerprint_scope', 'record_type + source_record_key + payload_sha256'
  ),
  jsonb_build_object(
    'publishes_payloads', false,
    'publishes_source_record_keys', false,
    'publishes_personal_identifiers', false
  )
);

notify pgrst, 'reload schema';

commit;
