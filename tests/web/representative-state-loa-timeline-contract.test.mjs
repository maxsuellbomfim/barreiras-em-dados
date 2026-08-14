import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);
const client = await readFile(
  new URL("../../apps/web/lib/parliamentary-transfers.ts", import.meta.url),
  "utf8",
);
const resources = await readFile(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

test("perfis consultam a contribuição estadual anual em uma única RPC", () => {
  assert.match(client, /getPublicStateLoaRepresentativeContributions/);
  assert.match(client, /get_public_bahia_state_loa_representative_contributions/);
  assert.match(page, /getPublicStateLoaRepresentativeContributions\(\)/);
  assert.match(page, /stateLoaContributionsForRepresentative/);
});

test("linha do tempo separa autorização da execução parcial e liga a evidência", () => {
  assert.match(page, /Emendas estaduais para Barreiras/);
  assert.match(page, /Autorizado na LOA/);
  assert.match(page, /Autorizado no subconjunto conciliado/);
  assert.match(page, /Empenhado no subconjunto conciliado/);
  assert.match(page, /Liquida..o no subconjunto conciliado/iu);
  assert.match(page, /Pago no subconjunto conciliado/);
  assert.match(page, /n.o atribu.da com seguran.a neste exerc.cio/iu);
  assert.match(page, /origem=estadual&ano=\$\{row\.fiscalYear\}/);
  assert.match(resources, /id=\{parliamentaryTransferAuthorAnchor\(row\.authorKey\)\}/);
});
