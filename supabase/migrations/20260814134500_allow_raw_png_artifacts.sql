begin;

-- O diagrama oficial de relacionamento do FIPLAN é publicado como PNG. O
-- bucket permanece privado e aceita o novo MIME apenas para preservar a
-- evidência com o tipo declarado pela fonte, sem reclassificá-la como binário.

update storage.buckets
set allowed_mime_types = array(
  select distinct mime_type
  from unnest(
    coalesce(allowed_mime_types, array[]::text[])
    || array['image/png']::text[]
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
  'migration:allow-raw-png-artifacts',
  'storage_bucket.mime_type_enabled',
  'storage.buckets',
  bucket.id,
  jsonb_build_object(
    'public', bucket.public,
    'allowed_mime_types', to_jsonb(bucket.allowed_mime_types)
  ),
  jsonb_build_object(
    'mime_type', 'image/png',
    'purpose', 'bahia_state_amendment_relationship_diagram'
  )
from storage.buckets as bucket
where bucket.id = 'raw-artifacts';

commit;
