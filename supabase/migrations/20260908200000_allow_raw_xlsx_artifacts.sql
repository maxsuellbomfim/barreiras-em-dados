begin;

-- O cadastro oficial do Farmácia Popular é publicado em XLSX.
-- O bucket continua privado e recebe apenas o MIME específico do formato
-- OOXML, cuja estrutura é validada pelo coletor antes da preservação.

with bucket_without_xlsx as (
  select bucket.id
  from storage.buckets as bucket
  where bucket.id = 'raw-artifacts'
    and not (
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      = any(coalesce(bucket.allowed_mime_types, array[]::text[]))
    )
), updated_bucket as (
  update storage.buckets as bucket
  set allowed_mime_types = array(
    select distinct allowed.mime_type
    from unnest(
      coalesce(bucket.allowed_mime_types, array[]::text[])
      || array[
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      ]::text[]
    ) as allowed(mime_type)
    order by allowed.mime_type
  )
  from bucket_without_xlsx
  where bucket.id = bucket_without_xlsx.id
  returning bucket.id, bucket.public, bucket.allowed_mime_types
)
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
  'migration:allow-raw-xlsx-artifacts',
  'storage_bucket.mime_type_enabled',
  'storage.buckets',
  bucket.id,
  jsonb_build_object(
    'public', bucket.public,
    'allowed_mime_types', to_jsonb(bucket.allowed_mime_types)
  ),
  jsonb_build_object(
    'mime_type',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'purpose', 'fns_pharmacy_official_register'
  )
from updated_bucket as bucket;

commit;
