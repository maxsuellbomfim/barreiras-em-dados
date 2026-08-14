import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const clientPath = new URL(
  "../../apps/web/lib/parliamentary-contribution-profiles.ts",
  import.meta.url,
);
const rankingPath = new URL(
  "../../apps/web/app/representantes/legislature-transfer-rankings.tsx",
  import.meta.url,
);
const pagePath = new URL(
  "../../apps/web/app/representantes/emendas/[sphere]/[legislatureNumber]/[authorKey]/page.tsx",
  import.meta.url,
);

test("requests one exact author and paginates the individual contribution RPC", async () => {
  const source = await readFile(clientPath, "utf8");
  assert.match(source, /get_public_parliamentary_legislature_contributions/u);
  assert.match(source, /author_key_filter:\s*normalizedAuthorKey/u);
  assert.match(source, /page_size:\s*PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE/u);
  assert.match(source, /page_offset:\s*\(page - 1\)/u);
});

test("links every ranked authorship to its evidence page", async () => {
  const source = await readFile(rankingPath, "utf8");
  assert.match(
    source,
    /\/representantes\/emendas\/\$\{group\.sphere\}\/\$\{group\.legislatureNumber\}\/\$\{encodeURIComponent\(row\.authorKey\)\}/u,
  );
  assert.match(source, /Ver emendas, valores e documentos/u);
});

test("explains missing stages as unavailable instead of zero", async () => {
  const source = await readFile(pagePath, "utf8");
  assert.match(source, /não localizado na fonte consultada/u);
  assert.match(source, /não publicado neste recorte federal/u);
  assert.match(source, /nunca é convertido em R\$ 0,00/u);
  assert.match(source, /valor destinado ou autorizado não\s+significa dinheiro pago/u);
});
