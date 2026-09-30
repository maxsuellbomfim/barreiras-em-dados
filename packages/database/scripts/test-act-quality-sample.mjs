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
assert.ok(
  migrationNames.some((name) => name.endsWith("_act_quality_sample.sql")),
  "migration da amostra de qualidade ausente",
);

const sha = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const q = (text) => text.replaceAll("'", "''");
const reviewer = "27b3add6-f788-48e5-bf6f-50dfbd8cf198";
const ruleset = "gazette-act-candidates/9.9.9";
const oldRuleset = "gazette-act-candidates/9.9.8";

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
      ('${reviewer}'),
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
    const migration = await readFile(fileURLToPath(new URL(name, migrationsUrl)), "utf8");
    await database.exec(migration);
  }

  // Fonte, endpoint e execução mínimos para os artefatos.
  await database.exec(`
    insert into source.data_sources (id, slug, name, authority_level, homepage_url)
    values ('00000000-0000-4000-a000-000000000001', 'teste-diario', 'Diário de teste',
            'official', 'https://barreiras.ba.gov.br')
    on conflict do nothing;
    insert into source.source_endpoints (id, data_source_id, slug, endpoint_kind, base_url)
    values ('00000000-0000-4000-a000-000000000002', '00000000-0000-4000-a000-000000000001',
            'pdf-teste', 'file', 'https://barreiras.ba.gov.br');
    insert into source.collection_runs (id, source_endpoint_id, idempotency_key,
      collector_version, parser_version, status, attempt_count, started_at, completed_at)
    values ('00000000-0000-4000-a000-000000000003', '00000000-0000-4000-a000-000000000002',
            '${"b".repeat(64)}', 'test/1', 'parser/1', 'succeeded', 1, now(), now());
  `);

  let counter = 0;
  const uuid = () => `00000000-0000-4000-b000-${String(++counter).padStart(12, "0")}`;
  const statements = [];
  function artifact(edition, pages, acts, version = ruleset) {
    const id = uuid();
    const artifactSha = sha(`pdf-${edition}`);
    statements.push(`insert into raw.raw_artifacts (id, collection_run_id, source_endpoint_id,
      idempotency_key, artifact_kind, source_url, retrieved_at, http_status, content_type,
      byte_size, sha256, object_key, collector_version, metadata)
      values ('${id}', '00000000-0000-4000-a000-000000000003', '00000000-0000-4000-a000-000000000002',
      '${sha(`idem-${edition}`)}', 'document', 'https://barreiras.ba.gov.br/diario${edition}.pdf',
      now(), 200, 'application/pdf', 10, '${artifactSha}', 'diario/${artifactSha}.pdf', 'test/1',
      '{"schema_name":"gazette-direct-edition","edition":"${edition}","year":"2025",
        "document_role":"pdf","final_url":"https://barreiras.ba.gov.br/diario${edition}.pdf"}');`);
    const parts = [];
    for (const page of pages) {
      statements.push(`insert into raw.document_pages (raw_artifact_id, page_number,
        parser_version, extraction_method, text_content)
        values ('${id}', ${page.number}, 'gazette-pdf-embedded-text/1.1.0', 'embedded_text',
        ${page.embedded === null ? "null" : `'${q(page.embedded)}'`});`);
      if (page.ocr) {
        statements.push(`insert into raw.document_pages (raw_artifact_id, page_number,
          parser_version, extraction_method, text_content)
          values ('${id}', ${page.number}, 'gazette-ocr-text/1.0.0', 'ocr', '${q(page.ocr)}');`);
      }
      const embeddedMissing =
        page.embedded === null || page.embedded.trim() === String(page.number);
      const part = embeddedMissing ? page.ocr : page.embedded;
      if (part) parts.push(part);
    }
    const canonical = parts.join("\n\n");
    const job = uuid();
    statements.push(`insert into raw.extraction_jobs (id, raw_artifact_id, job_type,
      idempotency_key, status, extractor_version) values ('${job}', '${id}',
      'gazette_act_candidates', '${sha(`job-${edition}`)}', 'succeeded', '${version}');`);
    const results = {};
    for (const act of acts) {
      const resultId = uuid();
      results[act.trigger] = resultId;
      const start = canonical.indexOf(act.trigger);
      assert.ok(start >= 0, act.trigger);
      const payload = {
        schema_name: "gazette-act-candidate",
        match_start: start,
        match_end: start + act.trigger.length,
        excerpt: `${act.trigger} CPF 123.456.789-09`,
        canonical_text_sha256: sha(canonical),
        fields: { person_name: { value: act.person } },
      };
      statements.push(`insert into raw.extraction_results (id, extraction_job_id,
        candidate_type, extractor_version, validator_version, result_payload, validation_status)
        values ('${resultId}', '${job}', '${act.type}', '${act.version ?? version}', 'v/1',
        '${q(JSON.stringify(payload))}', 'valid');`);
    }
    return { id, results, sha: artifactSha };
  }

  const withActs = artifact(
    100,
    [
      { number: 1, embedded: "PORTARIA 1\nNOMEAR Fulano de Tal para o cargo" },
      { number: 2, embedded: "2", ocr: "PORTARIA 2\nEXONERAR Beltrano do cargo" },
      { number: 3, embedded: "Aviso de licitação sem pessoal" },
    ],
    [
      { trigger: "NOMEAR Fulano", type: "nomeacao", person: "Fulano de Tal" },
      { trigger: "EXONERAR Beltrano", type: "exoneracao", person: "Beltrano" },
      // Resultado de régua antiga sobre o mesmo texto: fica fora da amostra.
      { trigger: "NOMEAR", type: "nomeacao", person: null, version: oldRuleset },
    ],
  );
  const plain = artifact(
    101,
    [
      { number: 1, embedded: "Ficou registrada a nomeação da comissão" },
      { number: 2, embedded: "Extrato de contrato" },
    ],
    [],
  );
  await database.exec(statements.join("\n"));

  const sampleId = (
    await database.query(`select editorial.create_act_quality_sample(
      'act-quality-sample/9.9.9', 'semente-de-teste', 5, '${ruleset}') as id`)
  ).rows[0].id;
  assert.ok(sampleId);

  const pages = await database.query(`
    select stratum, edition, page_number, text_source,
      (select count(*)::integer from editorial.act_quality_sample_acts a
       where a.sample_page_id = p.id) as acts
    from editorial.act_quality_sample_pages p
    where p.sample_id = '${sampleId}'
    order by edition, page_number`);
  assert.deepEqual(pages.rows, [
    { stratum: "act_embedded", edition: 100, page_number: 1, text_source: "embedded", acts: 1 },
    { stratum: "act_ocr", edition: 100, page_number: 2, text_source: "ocr", acts: 1 },
    { stratum: "other_embedded", edition: 100, page_number: 3, text_source: "embedded", acts: 0 },
    { stratum: "keyword_embedded", edition: 101, page_number: 1, text_source: "embedded", acts: 0 },
    { stratum: "other_embedded", edition: 101, page_number: 2, text_source: "embedded", acts: 0 },
  ]);
  const strata = (
    await database.query(`select strata from editorial.act_quality_samples where id = '${sampleId}'`)
  ).rows[0].strata;
  assert.deepEqual(strata.other_embedded, { population: 2, sampled: 2 });
  assert.deepEqual(strata._excluded, { unverified_artifacts: 0, unmapped_acts: 0 });

  // Criação automática: espera enquanto houver edição só com régua anterior.
  const ensure = async (version) =>
    (await database.query(`select editorial.ensure_act_quality_sample('${version}') as s`))
      .rows[0].s;
  assert.deepEqual(await ensure(ruleset), {
    status: "current",
    sample_version: "act-quality-sample/9.9.9",
  });

  // A amostra congelada não pode ser alterada.
  await assert.rejects(
    database.query(`update editorial.act_quality_sample_pages set page_number = 9`),
    /immutable relation/,
  );

  // Sem revisor ativo, nada é lido nem gravado.
  await assert.rejects(database.query("select * from api.get_act_quality_sample()"), /revisores ativos/);
  await database.exec(`
    insert into audit.reviewer_identities (auth_user_id, display_name, status, activated_at)
    values ('${reviewer}', 'Revisora de Teste', 'active', statement_timestamp());
    select set_config('request.jwt.claim.sub', '${reviewer}', false);
  `);
  const loaded = await database.query("select * from api.get_act_quality_sample()");
  assert.equal(loaded.rows.length, 5);
  const firstPage = loaded.rows.find((row) => row.edition === 100 && row.page_number === 1);
  assert.equal(firstPage.pdf_page_url, "https://barreiras.ba.gov.br/diario100.pdf#page=1");
  assert.equal(firstPage.acts[0].person_name, "Fulano de Tal");
  assert.doesNotMatch(firstPage.acts[0].excerpt, /123\.456\.789-09/, "CPF mascarado no trecho");

  const nomeacao = withActs.results["NOMEAR Fulano"];
  await assert.rejects(
    database.query(`select api.annotate_act_quality_page('${firstPage.sample_page_id}',
      '{}'::jsonb, 0, 0, null)`),
    /exatamente um veredito/,
  );
  await assert.rejects(
    database.query(`select api.annotate_act_quality_page('${firstPage.sample_page_id}',
      '{"${nomeacao}":"talvez"}'::jsonb, 0, 0, null)`),
    /correct, partial ou incorrect/,
  );
  await database.query(`select api.annotate_act_quality_page('${firstPage.sample_page_id}',
    '{"${nomeacao}":"correct"}'::jsonb, 0, 1, 'faltou uma exoneração')`);
  const ocrPage = loaded.rows.find((row) => row.page_number === 2 && row.edition === 100);
  const exoneracao = withActs.results["EXONERAR Beltrano"];
  await database.query(`select api.annotate_act_quality_page('${ocrPage.sample_page_id}',
    '{"${exoneracao}":"incorrect"}'::jsonb, 0, 0, null)`);
  const keywordPage = loaded.rows.find((row) => row.stratum === "keyword_embedded");
  await database.query(`select api.annotate_act_quality_page('${keywordPage.sample_page_id}',
    '{}'::jsonb, 1, 0, null)`);

  const metrics = await database.query("select * from api.get_act_quality_metrics()");
  const byScope = Object.fromEntries(metrics.rows.map((row) => [row.scope, row]));
  assert.equal(byScope["total:overall"].acts_judged, 2);
  assert.equal(byScope["total:overall"].acts_correct, 1);
  assert.equal(Number(byScope["total:overall"].precision_strict), 0.5);
  // Recall ponderado: 1 achado; perdidos 1 (página do ato) + 1 (palavra-chave).
  assert.equal(Number(byScope["total:overall"].recall_estimate), 0.3333);
  assert.equal(Number(byScope["total:nomeacao"].precision_strict), 1);
  assert.equal(Number(byScope["total:exoneracao"].precision_strict), 0);
  assert.equal(byScope["total:overall"].methodology_version, "act-quality-metrics/1.1.0");
  const annotated = await database.query(
    "select count(*)::integer as n from editorial.act_quality_annotations");
  assert.equal(annotated.rows[0].n, 3);

  // ADR 0091: anotação por IA, rotulada, gravada só pelo worker.
  const pending = await database.query(`select sample_page_id::text as id, acts
    from editorial.get_act_quality_pages_for_ai('act-quality-prompt/1.0.0', 50)`);
  assert.equal(pending.rows.length, 5, "a amostra da versão 9.9.9 é a atual");
  const aiPage = pending.rows.find((row) => row.id === firstPage.sample_page_id);
  assert.equal(aiPage.acts.length, 1);
  await assert.rejects(
    database.query(`select editorial.record_ai_act_quality_annotation(
      '${firstPage.sample_page_id}', '{"${nomeacao}":"correct"}'::jsonb, 0, 0,
      'humano-disfarcado', '${"a".repeat(64)}')`),
    /anotador de IA inválido/,
  );
  await database.query(`select editorial.record_ai_act_quality_annotation(
    '${firstPage.sample_page_id}', '{"${nomeacao}":"partial"}'::jsonb, 0, 0,
    'ai:gemini-2.5-flash:act-quality-prompt/1.0.0', '${"a".repeat(64)}')`);
  const stillPending = await database.query(`select count(*)::integer as n
    from editorial.get_act_quality_pages_for_ai('act-quality-prompt/1.0.0', 50)`);
  assert.equal(stillPending.rows[0].n, 4, "página anotada pela IA sai da fila da IA");
  const aiMetrics = Object.fromEntries(
    (await database.query("select * from api.get_act_quality_metrics('ai')")).rows
      .map((row) => [row.scope, row]),
  );
  assert.equal(aiMetrics["total:overall"].acts_judged, 1);
  assert.equal(Number(aiMetrics["total:overall"].precision_lenient), 1);
  assert.equal(aiMetrics["total:overall"].methodology_version, "act-quality-metrics/1.1.0");
  const humanMetrics = Object.fromEntries(
    (await database.query("select * from api.get_act_quality_metrics('human')")).rows
      .map((row) => [row.scope, row]),
  );
  assert.equal(humanMetrics["total:overall"].acts_judged, 2, "a IA não entra na conta humana");
  const reloaded = await database.query("select * from api.get_act_quality_sample()");
  const aiAnnotated = reloaded.rows.find((row) => row.sample_page_id === firstPage.sample_page_id);
  assert.equal(aiAnnotated.latest_annotation.annotator, "ai:gemini-2.5-flash:act-quality-prompt/1.0.0");
  const workerAccess = await database.query(`select
    has_function_privilege('collector_worker',
      'editorial.record_ai_act_quality_annotation(uuid,jsonb,integer,integer,text,text)', 'EXECUTE') as worker,
    has_function_privilege('authenticated',
      'editorial.record_ai_act_quality_annotation(uuid,jsonb,integer,integer,text,text)', 'EXECUTE') as reviewer`);
  assert.deepEqual(workerAccess.rows[0], { worker: true, reviewer: false });

  // Por último, porque a amostra nova passa a ser a atual.
  const nextRuleset = "gazette-act-candidates/9.10.0";
  assert.deepEqual(await ensure(nextRuleset), { status: "waiting", pending: 2, processed: 0 });
  await database.exec(`
    insert into raw.extraction_jobs (raw_artifact_id, job_type, idempotency_key, status,
      extractor_version)
    values ('${withActs.id}', 'gazette_act_candidates', '${sha("ocr-key-100")}', 'succeeded',
      '${nextRuleset}');`);
  assert.deepEqual(await ensure(nextRuleset), { status: "waiting", pending: 1, processed: 1 });
  // A segunda edição conclui pela chave histórica (sem OCR), sem a coluna.
  await database.exec(`
    insert into raw.extraction_jobs (raw_artifact_id, job_type, idempotency_key, status)
    values ('${plain.id}', 'gazette_act_candidates',
      encode(sha256(convert_to('gazette-acts:${plain.sha}:${nextRuleset}', 'UTF8')), 'hex'),
      'succeeded');`);
  // Três amostras já existem: a 1.0.0 da migration, a do teste e a nova.
  const created = await ensure(nextRuleset);
  assert.equal(created.status, "created");
  assert.equal(created.sample_version, "act-quality-sample/1.2.0");
  assert.deepEqual(await ensure(nextRuleset), {
    status: "current",
    sample_version: "act-quality-sample/1.2.0",
  });
  const ensureAccess = await database.query(`select
    has_function_privilege('collector_worker',
      'editorial.ensure_act_quality_sample(text)', 'EXECUTE') as worker,
    has_function_privilege('authenticated',
      'editorial.ensure_act_quality_sample(text)', 'EXECUTE') as reviewer`);
  assert.deepEqual(ensureAccess.rows[0], { worker: true, reviewer: false });
} finally {
  await database.close();
}

console.log("act quality sample migration test passed");
