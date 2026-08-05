import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const digestClient = await readFile(
  new URL("../../apps/web/lib/edition-digests.ts", import.meta.url),
  "utf8",
);
const diaryPage = await readFile(
  new URL("../../apps/web/app/diario/page.tsx", import.meta.url),
  "utf8",
);

test("resumo recebe metadados oficiais do catálogo da mesma edição", () => {
  assert.match(digestClient, /enrichEditionDigestsWithCatalog/);
  assert.match(digestClient, /catalog\.editionDate/);
  assert.match(digestClient, /catalog\.officialTitle/);
  assert.match(digestClient, /catalog\.officialSummary/);
  assert.match(diaryPage, /enrichEditionDigestsWithCatalog\(/);
});

