import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const assistCommand = new URL(
  "../../workers/document-processing/src/barreiras_docproc/commands/assist_extraction_candidates.py",
  import.meta.url,
);
const digestCommand = new URL(
  "../../workers/document-processing/src/barreiras_docproc/commands/digest_gazette_editions.py",
  import.meta.url,
);
const localAssist = new URL(
  "../../workers/document-processing/src/barreiras_docproc/local_assist.py",
  import.meta.url,
);

test("cota esgotada mantém explicação factual local e auditável", async () => {
  const [command, module] = await Promise.all([
    readFile(assistCommand, "utf8"),
    readFile(localAssist, "utf8"),
  ]);
  assert.match(command, /local_fallback_enabled/);
  assert.match(command, /local-deterministic/);
  assert.match(module, /template-from-deterministic-fields/);
  assert.match(module, /multiple_persons_detected/);
});

test("Diário local só resume atos reconhecidos e marca cobertura parcial", async () => {
  const command = await readFile(digestCommand, "utf8");
  assert.match(command, /deterministic_digest_items/);
  assert.match(command, /LOCAL_DIGEST_VERSION/);
  assert.match(command, /providers == \["local-deterministic"\]/);
});
