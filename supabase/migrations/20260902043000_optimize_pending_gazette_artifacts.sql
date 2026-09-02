begin;

-- A fila de processamento integral consultava todo o acervo JSON antes de
-- aplicar o limite. Estes índices parciais cobrem somente as duas famílias de
-- artefatos elegíveis e preservam a ordenação oficial mais recente primeiro.
create index if not exists raw_artifacts_gazette_direct_pending_idx
  on raw.raw_artifacts (
    ((metadata ->> 'year')::integer) desc,
    ((metadata ->> 'edition')::integer) desc,
    created_at desc,
    id desc
  )
  include (sha256)
  where metadata ->> 'schema_name' = 'gazette-direct-edition'
    and coalesce(metadata ->> 'edition', '') ~ '^[0-9]+$'
    and coalesce(metadata ->> 'year', '') ~ '^[0-9]{4}$';

create index if not exists raw_artifacts_querido_diario_txt_pending_idx
  on raw.raw_artifacts (
    (metadata ->> 'source_record_key'),
    created_at desc,
    id desc
  )
  include (sha256)
  where metadata ->> 'document_role' = 'txt'
    and metadata ? 'source_record_key';

-- Cada TXT precisa apenas da observação oficial mais recente da mesma chave.
-- O índice elimina o DISTINCT ON global que causava sort e timeout crescentes.
create index if not exists raw_records_querido_diario_latest_idx
  on raw.raw_records (
    source_record_key,
    collected_at desc,
    id desc
  )
  include (payload)
  where record_type = 'querido_diario_gazette'
    and source_record_key is not null;

commit;
