import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/ocr-gazette-backlog.yml", import.meta.url),
  "utf8",
);

test("dreno de OCR processa em lote e republica as edições que ganharam texto", () => {
  assert.match(workflow, /cron: "47,17 \* \* \* \*"/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /LIMIT_PAGES: \$\{\{ inputs\.limit_pages \|\| '800' \}\}/);
  // Um Tesseract de uma thread por página, 4 páginas em paralelo.
  assert.match(workflow, /OMP_THREAD_LIMIT: "1"/);
  assert.match(workflow, /--workers 4/);
  assert.match(workflow, /--limit-pages "\$\{LIMIT_PAGES\}"/);
  assert.doesNotMatch(workflow, /--limit-pages "\$\{\{ inputs\./);
  // OCR sem republicação deixaria o texto novo preso no acervo bruto.
  assert.ok(
    workflow.indexOf("ocr_gazette_pages") < workflow.indexOf("segment_gazette_editions"),
  );
  // Atos só depois da reorganização, e sem publicar direto daqui.
  assert.ok(
    workflow.indexOf("segment_gazette_editions") < workflow.indexOf("process_gazette_acts"),
  );
  assert.doesNotMatch(workflow, /publish_verified_candidates/);
  assert.match(workflow, /QUERIDO_DIARIO_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /permissions:\s*\n\s*contents: read/);
});

test("OCR do Diário usa o modelo tessdata_best fixado por commit e hash", async () => {
  for (const name of ["ocr-gazette-backlog", "backfill-gazette-acts", "collect-querido-diario"]) {
    const text = await readFile(
      new URL(`../../.github/workflows/${name}.yml`, import.meta.url),
      "utf8",
    );
    assert.match(text, /tessdata_best\/9ddc24e750eec0994223a9edc3fcb434a2244f3b\/por\.traineddata/, name);
    assert.match(text, /711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04 .*sha256sum -c -/, name);
    assert.ok(
      text.indexOf("GAZETTE_TESSDATA_DIR=") < text.indexOf("ocr_gazette_pages"),
      `${name}: modelo antes do OCR`,
    );
  }
});
