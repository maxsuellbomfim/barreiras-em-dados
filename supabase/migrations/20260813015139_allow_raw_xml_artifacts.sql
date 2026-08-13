-- O catálogo histórico do Transferegov é XML. O bucket continua privado e
-- aceita somente os MIME types explicitamente contratados.

update storage.buckets
set allowed_mime_types = array(
  select distinct mime_type
  from unnest(
    coalesce(allowed_mime_types, array[]::text[])
    || array['application/xml']::text[]
  ) as mime_type
  order by mime_type
)
where id = 'raw-artifacts';

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
  'migration:allow-raw-xml-artifacts',
  'storage_bucket.mime_type_enabled',
  'storage.buckets',
  bucket.id,
  jsonb_build_object(
    'public', bucket.public,
    'allowed_mime_types', to_jsonb(bucket.allowed_mime_types)
  ),
  jsonb_build_object(
    'mime_type', 'application/xml',
    'purpose', 'transferegov_download_catalog_raw_artifact'
  )
from storage.buckets as bucket
where bucket.id = 'raw-artifacts';
