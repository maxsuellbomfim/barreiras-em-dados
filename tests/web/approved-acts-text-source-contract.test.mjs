import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const lib = read("apps/web/lib/approved-acts.ts");
const explorer = read("apps/web/app/atos/act-explorer.tsx");
const migration = read("supabase/migrations/20260924000000_approved_acts_text_source.sql");

test("a projeção informa se o texto do ato veio de OCR", () => {
  assert.match(migration, /text_source text,\s*\n\s*methodology_version text/);
  assert.match(migration, /ocr_page\.extraction_method = 'ocr'/);
  assert.match(migration, /then 'ocr_transcription'\s*\n\s*else 'embedded_text'/);
  assert.match(migration, /'approved-gazette-acts\/1\.7\.0'::text/);
});

test("o site aceita as versões vizinhas e nunca presume texto embutido", () => {
  // Produção pode estar uma migration à frente ou atrás do deploy web.
  for (const version of ["1.6.0", "1.7.0"]) {
    assert.match(lib, new RegExp(`"approved-gazette-acts/${version.replaceAll(".", "\\.")}"`));
  }
  assert.match(lib, /: "unknown",/);
  assert.match(lib, /row\.text_source !== "embedded_text" &&\s*row\.text_source !== "ocr_transcription"/);
});

test("ato vindo de OCR pede conferência no documento oficial", () => {
  assert.match(explorer, /act\.textSource === "ocr_transcription" \? \(/);
  assert.match(explorer, /nomes ou números podem ter erro de\s+leitura/);
  assert.match(explorer, /contra a transcrição por OCR do documento oficial/);
});
