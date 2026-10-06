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
assert.ok(migrationNames.some((name) => name.endsWith("_camara_legislative_items_latest.sql")));

const sha = (text) => createHash("sha256").update(text).digest("hex");
const database = new PGlite({ extensions: { pgcrypto, pg_trgm } });
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
    create table storage.buckets (
      id text primary key, name text not null, public boolean not null default false,
      file_size_limit bigint, allowed_mime_types text[]
    );
    create table storage.objects (
      id uuid primary key, bucket_id text not null references storage.buckets(id),
      name text not null, unique(bucket_id, name)
    );
    alter table storage.objects enable row level security;
    grant usage on schema storage to authenticated;
    grant select, insert, update, delete on storage.objects to authenticated;
  `);
  for (const name of migrationNames) {
    await database.exec(await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8"));
  }

  const run = "00000000-0000-4000-a000-000000000003";
  await database.exec(`
    insert into source.data_sources (id, slug, name, authority_level, homepage_url)
    values ('00000000-0000-4000-a000-000000000001', 'teste-camara', 'Teste', 'official',
            'https://barreiras.ba.gov.br');
    insert into source.source_endpoints (id, data_source_id, slug, endpoint_kind, base_url)
    values ('00000000-0000-4000-a000-000000000002', '00000000-0000-4000-a000-000000000001',
            'teste', 'api', 'https://barreiras.ba.gov.br');
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('${run}', '00000000-0000-4000-a000-000000000002', '${"e".repeat(64)}',
            'test/1', 'parser/1', 'succeeded', 1, now(), now());
    insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id, idempotency_key,
      artifact_kind, source_url, retrieved_at, http_status, content_type, byte_size, sha256,
      object_key, collector_version, metadata)
    values ('00000000-0000-4000-b000-000000000001', '${run}',
      '00000000-0000-4000-a000-000000000002', '${sha("idem")}', 'http_response',
      'https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2016.zip',
      now(), 200, 'application/json', 2, '${sha("tse")}', 'tse/x.json', 'test/1', '{}');
  `);
  let count = 0;
  const record = (type, key, payload) => {
    count += 1;
    return database.query(`insert into raw.raw_records (raw_artifact_id, source_record_key,
      record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
      collected_at) values ('00000000-0000-4000-b000-000000000001', $1, $2, $3, $4::jsonb,
      $5, 'parser/1', $6, now())`,
    [key, type, count, JSON.stringify(payload), sha(`p${count}`), sha(`i${count}`)]);
  };
  const tse = (year, name, outcome) => record("tse_votacao_barreiras",
    `tse:votacao:${year}:${count}:1`,
    { ano: String(year), nome: name, cargo: "Vereador", situacao: outcome, nome_urna: name,
      partido: "X", turno: "1" });
  await tse(2016, "FRANCISCO BEZERRA SOBRINHO", "ELEITO POR QP");
  await tse(2016, "JOSÉ BARBOSA PIRES JUNIOR", "ELEITO POR MÉDIA");
  await tse(2016, "FULANO SUPLENTE", "SUPLENTE");
  await tse(2020, "EURICO QUEIROZ FILHO", "ELEITO POR QP");
  await record("cm_barreiras_vereador", "cm:vereador:1", { nome: "Eurico Queiroz Filho" });
  const indicacao = (id, author, date) => record("municipal_transparency_indicacoes",
    `indicacoes:${id}`, { id_indicacao: String(id), autoria: author, data_protocolo: date,
      informacoes: `Indico a necessidade ${id}.`, ativo: "1" });
  await indicacao(1, "Francisco Bezerra Sobrinho", "2018-03-01");
  await indicacao(2, "FRANCISCO BEZERRA SOBRINHO", "2019-05-02");
  await indicacao(3, "Francisco Bezerra Sobrinho", "2023-01-10");
  await indicacao(4, "DR.JOSÉ BARBOSA PIRES JR.", "2017-02-02");
  await indicacao(5, "Fulano Suplente", "2018-04-04");
  await indicacao(6, "Eurico Queiroz Filho", "2022-06-06");
  await indicacao(7, "Chico Bezerra", "2018-07-07");

  // Coleta antiga chegando depois não sobrescreve a versão mais recente.
  count += 1;
  await database.query(`insert into raw.raw_records (raw_artifact_id, source_record_key,
    record_type, record_index, payload, payload_sha256, parser_version, idempotency_key,
    collected_at) values ('00000000-0000-4000-b000-000000000001', 'indicacoes:1:velha',
    'municipal_transparency_indicacoes', $1, $2::jsonb, $3, 'parser/1', $4, '2020-01-01')`,
  [count, JSON.stringify({ id_indicacao: "1", autoria: "Outro Nome", data_protocolo: "2018-03-01",
    informacoes: "Versão antiga." }), sha(`p${count}`), sha(`i${count}`)]);
  const latestOne = (await database.query(`select author_name, author_key, raw_record_id is not null as traced
    from political.camara_legislative_items where item_kind = 'indicacao' and item_id = '1'`)).rows[0];
  assert.deepEqual(latestOne,
    { author_name: "Francisco Bezerra Sobrinho", author_key: "FRANCISCO BEZERRA SOBRINHO", traced: true });
  assert.equal((await database.query(
    "select count(*)::int as n from political.camara_legislative_items")).rows[0].n, 7);

  const key = async (value) => (await database.query(
    "select political.council_author_key_v1($1) as k", [value])).rows[0].k;
  assert.equal(await key("DR.JOSÉ BARBOSA PIRES JR."), "JOSE BARBOSA PIRES JUNIOR");
  assert.equal(await key("VEREADORA Maria das Graças  (PTB)."), "MARIA DAS GRACAS");
  assert.equal(await key("Ben-Hir Aires de Santana"), "BEN HIR AIRES DE SANTANA");
  assert.equal(await key("JUNIOR CESAR"), "JUNIOR CESAR", "não reescreve nome que já é Junior");

  const summary = async (kind = null, year = null) => (await database.query(
    "select * from api.get_camara_former_author_summary($1, $2, null)", [kind, year])).rows;
  const all = await summary();
  assert.deepEqual(
    all.map((row) => [row.author_name, row.elected_terms, Number(row.item_count)]),
    [
      ["FRANCISCO BEZERRA SOBRINHO", "2017–2020", 2],
      ["JOSÉ BARBOSA PIRES JUNIOR", "2017–2020", 1],
    ],
    "fora do mandato, suplente, apelido e vereador atual ficam de fora",
  );
  assert.equal(all[0].methodology_version, "council-former-authors/1.0.0");
  assert.match(all[0].source_url, /^https:\/\/cdn\.tse\.jus\.br\//);
  assert.deepEqual((await summary(null, 2018)).map((row) => Number(row.item_count)), [1]);
  assert.deepEqual(await summary("lei"), []);

  const page = async (author) => (await database.query(
    "select item_id from api.get_camara_legislative_page(50, 0, null, null, $1, null) order by item_id",
    [author])).rows.map((row) => row.item_id);
  assert.deepEqual(await page("FRANCISCO BEZERRA SOBRINHO"), ["1", "2", "3"]);
  assert.deepEqual(await page("JOSÉ BARBOSA PIRES JUNIOR"), ["4"]);

  const access = await database.query(`select
    has_function_privilege('anon', 'api.get_camara_former_author_summary(text, integer, text)', 'EXECUTE') as summary,
    has_function_privilege('anon', 'political.tse_council_mandates_v1()', 'EXECUTE') as mandates`);
  assert.deepEqual(access.rows[0], { summary: true, mandates: false });
} finally {
  await database.close();
}

console.log("council former authors migration test passed");
