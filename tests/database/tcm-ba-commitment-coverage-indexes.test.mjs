import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const migration = readFileSync(
  new URL(
    "../../supabase/migrations/20260904060000_optimize_tcm_commitment_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);

test("indexes the bounded TCM-BA commitment coverage inputs", () => {
  assert.match(
    migration,
    /raw_artifacts_tcm_ba_monthly_pdf_idx[\s\S]*metadata\s*->>\s*'schema_name'[\s\S]*tcm-ba-monthly-document/i,
  );
  assert.match(
    migration,
    /document_pages_tcm_ba_embedded_text_idx[\s\S]*parser_version\s*=\s*'gazette-pdf-embedded-text\/1\.1\.0'/i,
  );
  assert.match(
    migration,
    /document_pages_tcm_ba_ocr_text_idx[\s\S]*parser_version\s*=\s*'tcm-ba-document-ocr-text\/1\.0\.0'/i,
  );
  assert.match(
    migration,
    /extraction_jobs_tcm_ba_commitment_current_idx[\s\S]*job_type\s*=\s*'tcm_ba_commitment_candidates'/i,
  );
  assert.match(migration, /analyze\s+raw\.raw_artifacts/i);
  assert.match(migration, /analyze\s+raw\.document_pages/i);
  assert.match(migration, /analyze\s+raw\.extraction_jobs/i);
  assert.doesNotMatch(
    migration,
    /include\s*\([^)]*text_content[^)]*\)/i,
    "textos integrais podem exceder o limite físico de uma linha do índice",
  );
});
