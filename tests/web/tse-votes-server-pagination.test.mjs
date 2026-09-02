import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const [client, page, study] = await Promise.all([
  readFile(new URL("../../apps/web/lib/tse-votes.ts", import.meta.url), "utf8"),
  readFile(new URL("../../apps/web/app/representantes/page.tsx", import.meta.url), "utf8"),
  readFile(
    new URL("../../apps/web/app/representantes/territorial-votes-study.tsx", import.meta.url),
    "utf8",
  ),
]);

test("histórico eleitoral consulta somente uma página filtrada no servidor", () => {
  assert.match(client, /get_tse_barreiras_votes_study/);
  assert.match(client, /page_size:\s*pageSize/);
  assert.match(client, /page_offset:\s*\(page - 1\) \* pageSize/);
  assert.doesNotMatch(client, /maxPages/);
  assert.doesNotMatch(client, /for \(let pageNumber/);
  assert.match(page, /searchParams/);
  assert.match(page, /getTseBarreirasVotesStudy/);
  assert.match(study, /Os filtros são aplicados no servidor sobre todo o acervo/);
  assert.match(study, /Página \{page\} de/);
  assert.doesNotMatch(study, /\.slice\(0, 50\)/);
});

test("interface não soma votos enquanto turnos diferentes estiverem no recorte", () => {
  assert.match(study, /selecione um turno para somar votos/);
  assert.match(study, /votesTotal === null/);
});

