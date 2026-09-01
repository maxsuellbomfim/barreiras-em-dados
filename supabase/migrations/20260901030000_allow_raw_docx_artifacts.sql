begin;

-- Alguns atos de controle do e-TCM/BA são publicados oficialmente em DOCX.
-- O bucket continua privado e recebe apenas o MIME específico do formato
-- OOXML, cuja estrutura é validada pelo coletor antes da preservação.

with bucket_without_docx as (
  select bucket.id
  from storage.buckets as bucket
  where bucket.id = 'raw-artifacts'
    and not (
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      = any(coalesce(bucket.allowed_mime_types, array[]::text[]))
    )
), updated_bucket as (
  update storage.buckets as bucket
  set allowed_mime_types = array(
    select distinct allowed.mime_type
    from unnest(
      coalesce(bucket.allowed_mime_types, array[]::text[])
      || array[
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      ]::text[]
    ) as allowed(mime_type)
    order by allowed.mime_type
  )
  from bucket_without_docx
  where bucket.id = bucket_without_docx.id
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
  'migration:allow-raw-docx-artifacts',
  'storage_bucket.mime_type_enabled',
  'storage.buckets',
  bucket.id,
  jsonb_build_object(
    'public', bucket.public,
    'allowed_mime_types', to_jsonb(bucket.allowed_mime_types)
  ),
  jsonb_build_object(
    'mime_type',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'purpose', 'tcm_ba_official_control_document'
  )
from updated_bucket as bucket;

commit;
