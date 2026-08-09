import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const integralClient = await readFile(
  new URL("../../apps/web/lib/integral-gazette-documents.ts", import.meta.url),
  "utf8",
);
const diaryPage = await readFile(
  new URL("../../apps/web/app/diario/page.tsx", import.meta.url),
  "utf8",
);

test("edição integral recebe data e fonte oficial do catálogo", () => {
  assert.match(integralClient, /enrichIntegralGazetteEditions/);
  assert.match(integralClient, /catalog\.editionDate/);
  assert.match(integralClient, /officialPublicationUrl/);
  assert.match(diaryPage, /enrichIntegralGazetteEditions\(/);
});
