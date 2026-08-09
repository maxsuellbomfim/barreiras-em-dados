begin;

create table raw.document_blocks (
  id uuid primary key default gen_random_uuid(),
  document_page_id uuid not null references raw.document_pages(id),
  block_order integer not null check (block_order >= 0),
  text_content text not null check (length(text_content) > 0),
  text_sha256 text not null check (
    text_sha256 = encode(digest(text_content, 'sha256'), 'hex')
  ),
  bbox jsonb,
  extraction_method text not null check (
    extraction_method in (
      'embedded_layout', 'embedded_text', 'ocr', 'hybrid', 'manual'
    )
  ),
  extractor_version text not null,
  created_at timestamptz not null default statement_timestamp(),
  unique (document_page_id, block_order, extractor_version)
);

create index document_blocks_page_order_idx
  on raw.document_blocks (document_page_id, block_order, extractor_version);

create table editorial.gazette_document_versions (
  id uuid primary key default gen_random_uuid(),
  supersedes_id uuid references editorial.gazette_document_versions(id),
  raw_artifact_id uuid not null references raw.raw_artifacts(id),
  edition integer not null check (edition > 0),
  edition_year integer not null check (edition_year between 2000 and 2100),
  edition_date date,
  document_order integer not null check (document_order > 0),
  first_block_id uuid not null references raw.document_blocks(id),
  last_block_id uuid not null references raw.document_blocks(id),
  page_start integer not null check (page_start > 0),
  page_end integer not null check (page_end >= page_start),
  literal_title text not null check (length(btrim(literal_title)) > 0),
  document_type text,
  full_text text not null check (length(full_text) > 0),
  text_sha256 text not null check (
    text_sha256 = encode(digest(full_text, 'sha256'), 'hex')
  ),
  publication_status text not null check (
    publication_status in ('validated', 'edition_fallback', 'superseded', 'withdrawn')
  ),
  segmenter_version text not null,
  validator_version text not null,
  batch_idempotency_key text not null check (
    length(batch_idempotency_key) between 16 and 256
  ),
  idempotency_key text not null unique check (length(idempotency_key) between 16 and 256),
  created_at timestamptz not null default statement_timestamp(),
  published_at timestamptz,
  check (
    publication_status not in ('validated', 'edition_fallback')
    or published_at is not null
  )
);

create unique index gazette_document_versions_one_successor_idx
  on editorial.gazette_document_versions (supersedes_id)
  where supersedes_id is not null;
create index gazette_document_versions_edition_idx
  on editorial.gazette_document_versions (
    edition_year desc, edition desc, batch_idempotency_key, document_order
  );
create index gazette_document_versions_artifact_idx
  on editorial.gazette_document_versions (raw_artifact_id);
create index gazette_document_versions_first_block_idx
  on editorial.gazette_document_versions (first_block_id);
create index gazette_document_versions_last_block_idx
  on editorial.gazette_document_versions (last_block_id);
create index gazette_document_versions_supersedes_idx
  on editorial.gazette_document_versions (supersedes_id);

create table editorial.gazette_document_version_blocks (
  version_id uuid not null references editorial.gazette_document_versions(id),
  block_id uuid not null references raw.document_blocks(id),
  sequence_order integer not null check (sequence_order >= 0),
  created_at timestamptz not null default statement_timestamp(),
  primary key (version_id, block_id),
  unique (version_id, sequence_order)
);

create index gazette_document_version_blocks_block_idx
  on editorial.gazette_document_version_blocks (block_id);

alter table raw.document_blocks enable row level security;
alter table editorial.gazette_document_versions enable row level security;
alter table editorial.gazette_document_version_blocks enable row level security;
revoke all on table raw.document_blocks, editorial.gazette_document_versions,
  editorial.gazette_document_version_blocks
  from public, anon, authenticated;
grant select, insert on raw.document_blocks to collector_worker;
grant select, insert on editorial.gazette_document_versions to collector_worker;
grant select, insert on editorial.gazette_document_version_blocks to collector_worker;
create policy collector_worker_document_blocks_select on raw.document_blocks
  for select to collector_worker using (true);
create policy collector_worker_document_blocks_insert on raw.document_blocks
  for insert to collector_worker with check (true);
create policy collector_worker_gazette_document_versions_select
  on editorial.gazette_document_versions for select to collector_worker using (true);
create policy collector_worker_gazette_document_versions_insert
  on editorial.gazette_document_versions for insert to collector_worker with check (true);
create policy collector_worker_gazette_document_version_blocks_select
  on editorial.gazette_document_version_blocks for select to collector_worker using (true);
create policy collector_worker_gazette_document_version_blocks_insert
  on editorial.gazette_document_version_blocks for insert to collector_worker with check (true);

create function editorial.verify_gazette_document_version_integrity()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  target_version_id uuid;
  target_version editorial.gazette_document_versions%rowtype;
  linked_block_count integer;
  first_linked_block_id uuid;
  last_linked_block_id uuid;
  first_page_number integer;
  last_page_number integer;
  all_blocks_match_artifact boolean;
  expected_text text;
begin
  target_version_id := coalesce(
    (to_jsonb(new) ->> 'id')::uuid,
    (to_jsonb(new) ->> 'version_id')::uuid
  );
  select * into target_version
  from editorial.gazette_document_versions
  where id = target_version_id;

  select
    count(*)::integer,
    (array_agg(link.block_id order by link.sequence_order))[1],
    (array_agg(link.block_id order by link.sequence_order desc))[1],
    (array_agg(page.page_number order by link.sequence_order))[1],
    (array_agg(page.page_number order by link.sequence_order desc))[1],
    bool_and(page.raw_artifact_id = target_version.raw_artifact_id),
    string_agg(block.text_content, E'\n\n' order by link.sequence_order)
  into linked_block_count, first_linked_block_id, last_linked_block_id,
    first_page_number, last_page_number, all_blocks_match_artifact, expected_text
  from editorial.gazette_document_version_blocks as link
  join raw.document_blocks as block on block.id = link.block_id
  join raw.document_pages as page on page.id = block.document_page_id
  where link.version_id = target_version_id;

  if linked_block_count is null or linked_block_count = 0
    or not exists (
      select 1
      from editorial.gazette_document_version_blocks as link
      where link.version_id = target_version_id
      group by link.version_id
      having min(link.sequence_order) = 0
        and max(link.sequence_order) = count(*) - 1
    ) then
    raise exception 'document block sequence is incomplete';
  end if;
  if not all_blocks_match_artifact then
    raise exception 'document blocks must belong to the version raw artifact';
  end if;
  if exists (
    select 1
    from (
      select page.page_number, block.block_order,
        lag(row(page.page_number, block.block_order)) over (
          order by link.sequence_order
        ) as previous_position
      from editorial.gazette_document_version_blocks as link
      join raw.document_blocks as block on block.id = link.block_id
      join raw.document_pages as page on page.id = block.document_page_id
      where link.version_id = target_version_id
    ) as ordered_blocks
    where previous_position >= row(page_number, block_order)
  ) then
    raise exception 'document block sequence is not in source order';
  end if;
  if target_version.first_block_id <> first_linked_block_id
    or target_version.last_block_id <> last_linked_block_id then
    raise exception 'document first and last blocks must match the literal sequence';
  end if;
  if target_version.page_start <> first_page_number
    or target_version.page_end <> last_page_number then
    raise exception 'document page interval does not match literal blocks';
  end if;
  if expected_text is null or expected_text <> target_version.full_text then
    raise exception 'full_text does not match literal blocks';
  end if;
  if position(target_version.literal_title in target_version.full_text) = 0 then
    raise exception 'literal_title is not present in full_text';
  end if;
  return null;
end;
$function$;

create constraint trigger verify_literal_block_coverage
after insert on editorial.gazette_document_versions
deferrable initially deferred
for each row execute function editorial.verify_gazette_document_version_integrity();
create constraint trigger verify_literal_block_coverage
after insert on editorial.gazette_document_version_blocks
deferrable initially deferred
for each row execute function editorial.verify_gazette_document_version_integrity();

create trigger reject_mutation
before update or delete on raw.document_blocks
for each row execute function audit.reject_mutation();
create trigger reject_mutation
before update or delete on editorial.gazette_document_versions
for each row execute function audit.reject_mutation();
create trigger reject_mutation
before update or delete on editorial.gazette_document_version_blocks
for each row execute function audit.reject_mutation();

create function api.get_integral_gazette_editions(page_size integer default 20)
returns table (
  edition integer,
  edition_year integer,
  edition_date date,
  artifact_sha256 text,
  documents jsonb,
  methodology_version text
)
language plpgsql stable security definer set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100' using errcode = '22023';
  end if;
  return query
  with all_batches as (
    -- A fonte direta vence replays do Querido Diário da mesma edição; dentro
    -- da mesma proveniência, a versão mais recente é a vigente.
    select distinct on (version.edition_year, version.edition)
      version.edition, version.edition_year, version.batch_idempotency_key
    from editorial.gazette_document_versions as version
    join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
    order by version.edition_year, version.edition,
      case when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then 0 else 1 end,
      version.created_at desc, version.id desc
  ), public_versions as (
    select version.*
    from editorial.gazette_document_versions as version
    where version.publication_status in ('validated', 'edition_fallback')
      and version.published_at is not null
  )
  select edition_record.edition, edition_record.edition_year,
    max(version.edition_date), artifact.sha256,
    jsonb_agg(jsonb_build_object(
      'document_id', version.id,
      'document_order', version.document_order,
      'literal_title', version.literal_title,
      'document_type', version.document_type,
      'page_start', version.page_start,
      'page_end', version.page_end,
      'full_text', version.full_text,
      'text_sha256', version.text_sha256,
      'publication_status', version.publication_status
    ) order by version.document_order),
    'integral-gazette-documents/1.0.0'::text
  from all_batches as edition_record
  join public_versions as version
    on version.edition = edition_record.edition
   and version.edition_year = edition_record.edition_year
   and version.batch_idempotency_key = edition_record.batch_idempotency_key
  join raw.raw_artifacts as artifact on artifact.id = version.raw_artifact_id
  group by edition_record.edition, edition_record.edition_year, artifact.sha256
  order by edition_record.edition_year desc, edition_record.edition desc
  limit page_size;
end;
$function$;

revoke all on function api.get_integral_gazette_editions(integer) from public;
grant execute on function api.get_integral_gazette_editions(integer) to anon, authenticated;
comment on function api.get_edition_digests(integer) is
  'DEPRECATED: compatibilidade temporária até a substituição atômica da interface pública.';
comment on table raw.document_blocks is
  'Blocos literais append-only derivados de páginas preservadas do Diário.';
comment on table editorial.gazette_document_versions is
  'Versões append-only de documentos integrais; supersessão ocorre por nova linha.';
comment on table editorial.gazette_document_version_blocks is
  'Sequência literal append-only que fixa os blocos exatos de cada versão documental.';

commit;
