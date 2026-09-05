import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { PGlite } from "@electric-sql/pglite";
import { pg_trgm } from "@electric-sql/pglite/contrib/pg_trgm";
import { pgcrypto } from "@electric-sql/pglite/contrib/pgcrypto";

const migrationsUrl = new URL("../../../supabase/migrations/", import.meta.url);
const migrationNames = (await readdir(fileURLToPath(migrationsUrl)))
  .filter((name) => name.endsWith(".sql"))
  .sort();
const migrations = await Promise.all(
  migrationNames.map((name) => readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8")),
);
const seed = await readFile(fileURLToPath(new URL("../../../supabase/seed.sql", import.meta.url)), "utf8");
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });

const artifactId = "00000000-0000-0000-0000-000000004706";
const pageId = "00000000-0000-0000-0000-000000000706";
const hybridPageId = "00000000-0000-0000-0000-000000000705";
const blockId = "00000000-0000-0000-0000-000000000806";
const hybridBlockId = "00000000-0000-0000-0000-000000000805";
const latePageOneBlockId = "00000000-0000-0000-0000-000000000804";
const latePageTwoBlockId = "00000000-0000-0000-0000-000000000803";
const correctedArtifactId = "00000000-0000-0000-0000-000000004707";
const correctedPageId = "00000000-0000-0000-0000-000000000707";
const correctedBlockId = "00000000-0000-0000-0000-000000000807";
const secondBlockId = "00000000-0000-0000-0000-000000000808";
const oldVersionId = "00000000-0000-0000-0000-000000000906";
const currentVersionId = "00000000-0000-0000-0000-000000000907";
const secondVersionId = "00000000-0000-0000-0000-000000000908";
const qdArtifactId = "00000000-0000-0000-0000-000000004708";
const qdPageId = "00000000-0000-0000-0000-000000000708";
const qdBlockId = "00000000-0000-0000-0000-000000000809";
const qdVersionId = "00000000-0000-0000-0000-000000000909";
const withdrawnVersionId = "00000000-0000-0000-0000-000000000910";
const shaA = "a".repeat(64);
const originalText = "PORTARIA N 261\nTexto integral oficial.";
const correctedText = "PORTARIA N 261\nTexto integral corrigido.";
const secondText = "DECRETO N 1\nTexto integral do segundo documento.";
const hybridText = "Página híbrida preservada.";
const originalMixedText = `${originalText}\n\n${hybridText}`;
const latePageOneText = "Trecho tardio da primeira página.";
const latePageTwoText = "Trecho tardio da segunda página.";
const outOfOrderText = `${originalText}\n\n${hybridText}\n\n${latePageOneText}\n\n${latePageTwoText}`;
const originalTextSha = createHash("sha256").update(originalText, "utf8").digest("hex");
const originalMixedTextSha = createHash("sha256").update(originalMixedText, "utf8").digest("hex");
const outOfOrderTextSha = createHash("sha256").update(outOfOrderText, "utf8").digest("hex");
const correctedTextSha = createHash("sha256").update(correctedText, "utf8").digest("hex");
const secondTextSha = createHash("sha256").update(secondText, "utf8").digest("hex");
const hybridTextSha = createHash("sha256").update(hybridText, "utf8").digest("hex");
const batchKey = "c".repeat(64);

async function rejects(sql, pattern = undefined) {
  await assert.rejects(database.exec(sql), pattern);
}

try {
  await database.exec(`
    create role anon nologin;
    create role authenticated nologin;
    create role authenticator nologin;
    create role service_role nologin bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key);
    insert into auth.users (id) values
      ('1575c740-fcff-4b1a-89a9-e8e5a314880a'),
      ('27b3add6-f788-48e5-bf6f-50dfbd8cf198'),
      ('c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a');
    create function auth.uid() returns uuid language sql stable set search_path = ''
      as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    create function auth.jwt() returns jsonb language sql stable set search_path = ''
      as $$ select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb) $$;
    create schema storage;
    create table storage.buckets (id text primary key, name text not null, public boolean not null default false, file_size_limit bigint, allowed_mime_types text[]);
    create table storage.objects (id uuid primary key, bucket_id text not null references storage.buckets(id), name text not null, unique(bucket_id, name));
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const migration of migrations) await database.exec(migration);
  await database.exec(seed);

  await database.exec(`
    begin;
    insert into source.collection_runs (
      id, source_endpoint_id, idempotency_key, collector_version, status
    ) values (
      '00000000-0000-0000-0000-000000000706',
      '00000000-0000-4000-8000-000000000101',
      'integral-gazette-fixture-4706', 'test/1', 'succeeded'
    );
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version,
      metadata
    ) values (
      '${artifactId}', '00000000-0000-0000-0000-000000000706',
      '00000000-0000-4000-8000-000000000101',
      'integral-gazette-artifact-fixture-4706', 'document',
      'https://barreiras.ba.gov.br/diario/pdf/2026/diario4706.pdf',
      statement_timestamp(), 18, '${shaA}', 'fixtures/gazette-4706.pdf', 'test/1',
      '{"schema_name":"gazette-direct-edition","edition":"4706","year":"2026","date":"2026-08-08"}'::jsonb
    );
    insert into raw.document_pages (
      id, raw_artifact_id, page_number, parser_version, extraction_method,
      text_content, text_sha256
    ) values (
      '${pageId}', '${artifactId}', 1, 'layout/1', 'embedded_text',
      'PORTARIA N 261\nTexto integral oficial.', '${originalTextSha}'
    );
    insert into raw.document_blocks (
      id, document_page_id, block_order, text_content, text_sha256,
      extraction_method, extractor_version
    ) values (
      '${blockId}', '${pageId}', 0, 'PORTARIA N 261\nTexto integral oficial.',
      '${originalTextSha}', 'embedded_text', 'layout/1'
    );
    insert into raw.document_pages (
      id, raw_artifact_id, page_number, parser_version, extraction_method,
      text_content, text_sha256
    ) values (
      '${hybridPageId}', '${artifactId}', 2, 'hybrid/1', 'hybrid',
      '${hybridText}', '${hybridTextSha}'
    );
    insert into raw.document_blocks (
      id, document_page_id, block_order, text_content, text_sha256,
      extraction_method, extractor_version
    ) values (
      '${hybridBlockId}', '${hybridPageId}', 0, '${hybridText}',
      '${hybridTextSha}', 'hybrid', 'hybrid/1'
    );
    insert into raw.document_blocks (
      id, document_page_id, block_order, text_content, text_sha256,
      extraction_method, extractor_version
    ) values
      ('${latePageOneBlockId}', '${pageId}', 1, '${latePageOneText}',
       encode(digest('${latePageOneText}', 'sha256'), 'hex'), 'embedded_text', 'layout/1'),
      ('${latePageTwoBlockId}', '${hybridPageId}', 1, '${latePageTwoText}',
       encode(digest('${latePageTwoText}', 'sha256'), 'hex'), 'hybrid', 'hybrid/1');
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, edition_date, document_order,
      first_block_id, last_block_id, page_start, page_end, literal_title,
      full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, published_at
    ) values (
      '${oldVersionId}', '${artifactId}', 4706, 2026, '2026-08-08', 1,
      '${blockId}', '${hybridBlockId}', 1, 2, 'PORTARIA N 261',
      '${originalMixedText}', '${originalMixedTextSha}', 'validated',
      'segmenter/1', 'validator/1', '${batchKey}', '${"d".repeat(64)}', statement_timestamp()
    );
    insert into editorial.gazette_document_version_blocks (
      version_id, block_id, sequence_order
    ) values
      ('${oldVersionId}', '${blockId}', 0),
      ('${oldVersionId}', '${hybridBlockId}', 1);
    commit;
  `);

  const relations = await database.query(`
    select to_regclass('raw.document_blocks')::text as blocks,
           to_regclass('editorial.gazette_document_versions')::text as versions,
           to_regclass('editorial.gazette_document_version_blocks')::text as version_blocks
  `);
  assert.deepEqual(relations.rows, [{
    blocks: "raw.document_blocks",
    versions: "editorial.gazette_document_versions",
    version_blocks: "editorial.gazette_document_version_blocks",
  }]);

  const rls = await database.query(`
    select
      (select relrowsecurity from pg_class where oid = 'raw.document_blocks'::regclass) as blocks_rls,
      (select relrowsecurity from pg_class where oid = 'editorial.gazette_document_version_blocks'::regclass) as version_blocks_rls
  `);
  assert.deepEqual(rls.rows[0], { blocks_rls: true, version_blocks_rls: true });
  const access = await database.query(`
    select
      has_table_privilege('anon', 'raw.document_blocks', 'select') as direct_blocks,
      has_table_privilege('anon', 'editorial.gazette_document_versions', 'select') as direct_versions,
      has_table_privilege('anon', 'editorial.gazette_document_version_blocks', 'select') as direct_version_blocks,
      has_function_privilege('anon', 'api.get_integral_gazette_editions(integer)', 'execute') as rpc,
      has_function_privilege('anon', 'api.get_edition_digests(integer)', 'execute') as legacy_rpc
  `);
  assert.deepEqual(access.rows, [{ direct_blocks: false, direct_versions: false, direct_version_blocks: false, rpc: true, legacy_rpc: true }]);
  await database.exec("set role anon");
  await rejects("select * from raw.document_blocks", /permission denied/);
  await database.exec("reset role");

  await rejects(`update raw.document_blocks set text_content = 'alterado' where id = '${blockId}'`, /immutable relation/);
  await rejects(`delete from raw.document_blocks where id = '${blockId}'`, /immutable relation/);
  await rejects(`
    begin;
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, document_order, first_block_id, last_block_id,
      page_start, page_end, literal_title, full_text, text_sha256, publication_status,
      segmenter_version, validator_version, batch_idempotency_key, idempotency_key, published_at
    ) values ('00000000-0000-0000-0000-000000000904', '${artifactId}', 4706, 2026, 1, '${blockId}', '${blockId}', 1, 1,
      'PORTARIA N 261', '${correctedText}', '${correctedTextSha}', 'validated', 'segmenter/2',
      'validator/1', '${"k".repeat(64)}', '${"l".repeat(64)}', statement_timestamp())
    ;
    insert into editorial.gazette_document_version_blocks (version_id, block_id, sequence_order)
    values ('00000000-0000-0000-0000-000000000904', '${blockId}', 0);
    commit;
  `, /full_text does not match literal blocks/);
  await rejects(`
    begin;
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, document_order, first_block_id, last_block_id,
      page_start, page_end, literal_title, full_text, text_sha256, publication_status,
      segmenter_version, validator_version, batch_idempotency_key, idempotency_key, published_at
    ) values ('00000000-0000-0000-0000-000000000903', '${artifactId}', 4706, 2026, 9, '${blockId}', '${latePageTwoBlockId}', 1, 2,
      'PORTARIA N 261', '${outOfOrderText}', '${outOfOrderTextSha}', 'validated', 'segmenter/2',
      'validator/1', '${"r".repeat(64)}', '${"s".repeat(64)}', statement_timestamp());
    insert into editorial.gazette_document_version_blocks (version_id, block_id, sequence_order)
    values
      ('00000000-0000-0000-0000-000000000903', '${blockId}', 0),
      ('00000000-0000-0000-0000-000000000903', '${hybridBlockId}', 1),
      ('00000000-0000-0000-0000-000000000903', '${latePageOneBlockId}', 2),
      ('00000000-0000-0000-0000-000000000903', '${latePageTwoBlockId}', 3);
    commit;
  `, /document block sequence is not in source order/);
  await rejects(`
    insert into editorial.gazette_document_versions (
      raw_artifact_id, edition, edition_year, document_order, first_block_id, last_block_id,
      page_start, page_end, literal_title, full_text, text_sha256, publication_status,
      segmenter_version, validator_version, batch_idempotency_key, idempotency_key
    ) values ('${artifactId}', 4706, 2026, 2, '${blockId}', '${blockId}', 1, 1,
      'PORTARIA N 262', 'Texto integral', '${originalTextSha}', 'validated', 'segmenter/1',
      'validator/1', '${"e".repeat(64)}', '${"f".repeat(64)}')
  `);

  await database.exec(`
    begin;
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version,
      metadata
    ) values (
      '${correctedArtifactId}', '00000000-0000-0000-0000-000000000706',
      '00000000-0000-4000-8000-000000000101',
      'integral-gazette-artifact-fixture-4706-corrected', 'document',
      'https://barreiras.ba.gov.br/diario/pdf/2026/diario4706-corrected.pdf',
      statement_timestamp(), 18, '${"c".repeat(64)}', 'fixtures/gazette-4706-corrected.pdf', 'test/2',
      '{"schema_name":"gazette-direct-edition","edition":"4706","year":"2026","date":"2026-08-08"}'::jsonb
    );
    insert into raw.document_pages (
      id, raw_artifact_id, page_number, parser_version, extraction_method,
      text_content, text_sha256
    ) values (
      '${correctedPageId}', '${correctedArtifactId}', 1, 'layout/2', 'embedded_text',
      '${correctedText}\n\n${secondText}',
      encode(digest('${correctedText}\n\n${secondText}', 'sha256'), 'hex')
    );
    insert into raw.document_blocks (
      id, document_page_id, block_order, text_content, text_sha256,
      extraction_method, extractor_version
    ) values
      ('${correctedBlockId}', '${correctedPageId}', 0, '${correctedText}',
       '${correctedTextSha}', 'embedded_text', 'layout/2'),
      ('${secondBlockId}', '${correctedPageId}', 1, '${secondText}',
       '${secondTextSha}', 'embedded_text', 'layout/2');
    insert into editorial.gazette_document_versions (
      id, supersedes_id, raw_artifact_id, edition, edition_year, edition_date,
      document_order, first_block_id, last_block_id, page_start, page_end,
      literal_title, full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, published_at
    ) values (
      '${currentVersionId}', '${oldVersionId}', '${correctedArtifactId}', 4706, 2026, '2026-08-08',
      1, '${correctedBlockId}', '${correctedBlockId}', 1, 1, 'PORTARIA N 261',
      'PORTARIA N 261\nTexto integral corrigido.', '${correctedTextSha}', 'validated',
      'segmenter/2', 'validator/1', '${"g".repeat(64)}', '${"h".repeat(64)}', statement_timestamp()
    );
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, edition_date, document_order,
      first_block_id, last_block_id, page_start, page_end, literal_title,
      full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, published_at
    ) values (
      '${secondVersionId}', '${correctedArtifactId}', 4706, 2026, '2026-08-08', 2,
      '${secondBlockId}', '${secondBlockId}', 1, 1, 'DECRETO N 1',
      '${secondText}', '${secondTextSha}', 'validated',
      'segmenter/2', 'validator/1', '${"g".repeat(64)}', '${"m".repeat(64)}', statement_timestamp()
    );
    insert into editorial.gazette_document_versions (
      raw_artifact_id, edition, edition_year, document_order,
      first_block_id, last_block_id, page_start, page_end, literal_title,
      full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, created_at
    ) values
      ('${correctedArtifactId}', 4706, 2026, 3,
       '${secondBlockId}', '${secondBlockId}', 1, 1, 'DECRETO N 1',
       '${secondText}', '${secondTextSha}', 'superseded', 'segmenter/3',
       'validator/1', '${"n".repeat(64)}', '${"o".repeat(64)}', statement_timestamp() - interval '1 day'),
      ('${correctedArtifactId}', 4706, 2026, 4,
       '${secondBlockId}', '${secondBlockId}', 1, 1, 'DECRETO N 1',
       '${secondText}', '${secondTextSha}', 'withdrawn', 'segmenter/3',
       'validator/1', '${"p".repeat(64)}', '${"q".repeat(64)}', statement_timestamp() - interval '1 day');
    insert into editorial.gazette_document_version_blocks (version_id, block_id, sequence_order)
    values
      ('${currentVersionId}', '${correctedBlockId}', 0),
      ('${secondVersionId}', '${secondBlockId}', 0),
      ((select id from editorial.gazette_document_versions where idempotency_key = '${"o".repeat(64)}'), '${secondBlockId}', 0),
      ((select id from editorial.gazette_document_versions where idempotency_key = '${"q".repeat(64)}'), '${secondBlockId}', 0);
    commit;
  `);
  await rejects(
    `update editorial.gazette_document_versions set literal_title = 'alterado' where id = '${currentVersionId}'`,
    /immutable relation/
  );
  await rejects(
    `update editorial.gazette_document_version_blocks set sequence_order = 1 where version_id = '${currentVersionId}'`,
    /immutable relation/
  );
  await rejects(
    `delete from editorial.gazette_document_version_blocks where version_id = '${currentVersionId}'`,
    /immutable relation/
  );
  await rejects(
    `delete from editorial.gazette_document_versions where id = '${currentVersionId}'`,
    /immutable relation/
  );
  await rejects(`
    insert into editorial.gazette_document_versions (
      supersedes_id, raw_artifact_id, edition, edition_year, document_order,
      first_block_id, last_block_id, page_start, page_end, literal_title, full_text,
      text_sha256, publication_status, segmenter_version, validator_version,
      batch_idempotency_key, idempotency_key, published_at
    ) values ('${oldVersionId}', '${artifactId}', 4706, 2026, 1, '${blockId}', '${blockId}',
      1, 1, 'PORTARIA N 261', '${originalText}', '${originalTextSha}', 'validated', 'segmenter/3', 'validator/1',
      '${"i".repeat(64)}', '${"j".repeat(64)}', statement_timestamp())
  `, /gazette_document_versions_one_successor_idx/);

  const projection = await database.query("select * from api.get_integral_gazette_editions(20)");
  assert.equal(projection.rows.length, 1);
  assert.deepEqual(
    projection.rows[0].documents.map((document) => document.document_id),
    [currentVersionId, secondVersionId]
  );
  for (const document of projection.rows[0].documents) {
    assert.deepEqual(Object.keys(document).sort(), [
      "document_id", "document_order", "document_type", "full_text", "literal_title",
      "page_end", "page_start", "publication_status", "text_sha256",
    ]);
  }
  const document = projection.rows[0].documents[0];
  assert.equal(document.document_id, currentVersionId);
  assert.equal(document.publication_status, "validated");
  assert.equal("confidence" in document, false);
  assert.equal("prompt" in document, false);
  await rejects("select * from api.get_integral_gazette_editions(0)", /page_size deve estar entre 1 e 100/);

  await database.exec(`
    begin;
    insert into raw.raw_artifacts (
      id, collection_run_id, source_endpoint_id, idempotency_key, artifact_kind,
      source_url, retrieved_at, byte_size, sha256, object_key, collector_version, metadata
    ) values (
      '${qdArtifactId}', '00000000-0000-0000-0000-000000000706',
      '00000000-0000-4000-8000-000000000101', 'integral-gazette-qd-fixture-4706', 'document',
      'https://queridodiario.ok.org.br/4706.txt', statement_timestamp(), 18, '${"b".repeat(64)}',
      'fixtures/gazette-4706.txt', 'test/3', '{"document_role":"txt"}'::jsonb
    );
    insert into raw.document_pages (
      id, raw_artifact_id, page_number, parser_version, extraction_method, text_content, text_sha256
    ) values ('${qdPageId}', '${qdArtifactId}', 1, 'ocr/9', 'ocr', '${secondText}', '${secondTextSha}');
    insert into raw.document_blocks (
      id, document_page_id, block_order, text_content, text_sha256, extraction_method, extractor_version
    ) values ('${qdBlockId}', '${qdPageId}', 0, '${secondText}', '${secondTextSha}', 'ocr', 'ocr/9');
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, edition_date, document_order, first_block_id, last_block_id,
      page_start, page_end, literal_title, full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, published_at, created_at
    ) values (
      '${qdVersionId}', '${qdArtifactId}', 4706, 2026, '2026-08-08', 1, '${qdBlockId}', '${qdBlockId}',
      1, 1, 'DECRETO N 1', '${secondText}', '${secondTextSha}', 'validated', 'segmenter/9', 'validator/1',
      '${"t".repeat(64)}', '${"u".repeat(64)}', statement_timestamp(), statement_timestamp() + interval '1 day'
    );
    insert into editorial.gazette_document_version_blocks (version_id, block_id, sequence_order)
    values ('${qdVersionId}', '${qdBlockId}', 0);
    commit;
  `);
  const directStillWins = await database.query("select * from api.get_integral_gazette_editions(20)");
  assert.deepEqual(
    directStillWins.rows[0].documents.map((item) => item.document_id),
    [currentVersionId, secondVersionId],
  );

  await database.exec(`
    begin;
    insert into editorial.gazette_document_versions (
      id, raw_artifact_id, edition, edition_year, edition_date, document_order, first_block_id, last_block_id,
      page_start, page_end, literal_title, full_text, text_sha256, publication_status, segmenter_version,
      validator_version, batch_idempotency_key, idempotency_key, created_at
    ) values (
      '${withdrawnVersionId}', '${correctedArtifactId}', 4706, 2026, '2026-08-08', 1,
      '${correctedBlockId}', '${correctedBlockId}', 1, 1, 'PORTARIA N 261', '${correctedText}',
      '${correctedTextSha}', 'withdrawn', 'segmenter/4', 'validator/1', '${"v".repeat(64)}',
      '${"w".repeat(64)}', statement_timestamp() + interval '2 days'
    );
    insert into editorial.gazette_document_version_blocks (version_id, block_id, sequence_order)
    values ('${withdrawnVersionId}', '${correctedBlockId}', 0);
    commit;
  `);
  const withdrawnBatchIsNotPublic = await database.query("select * from api.get_integral_gazette_editions(20)");
  assert.equal(withdrawnBatchIsNotPublic.rows.length, 0);

  console.log("Migration integral do Diário: seed, RLS, imutabilidade, versão e API verificados.");
} finally {
  await database.close();
}
