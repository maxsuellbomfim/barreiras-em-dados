import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);
const study = await readFile(
  new URL("../../apps/web/app/representantes/territorial-votes-study.tsx", import.meta.url),
  "utf8",
);

test("mandatos atuais aparecem antes do histórico eleitoral na ordem de leitura", () => {
  const executive = page.indexOf('id="executivo"');
  const councillors = page.indexOf('id="vereadores"');
  const state = page.indexOf('id="estaduais"');
  const federal = page.indexOf('id="federais"');
  const history = page.indexOf('id="vinculo"');

  assert.ok(executive < councillors);
  assert.ok(councillors < state);
  assert.ok(state < federal);
  assert.ok(federal < history);
  assert.match(page, /Mandatos municipais atuais/);
  assert.match(page, /Mandatos estaduais atuais/);
  assert.match(page, /Mandatos federais atuais/);
  assert.match(page, /selectFederalRepresentativesForOverview/);
  assert.match(page, /dez deputados federais atuais mais votados em Barreiras/);
  assert.doesNotMatch(page, /\{result\.representatives\.map\(/);
});

test("histórico explicita cargo, pleito e resultado sem declarar mandato atual", () => {
  assert.match(study, /Candidatura não é mandato atual/);
  assert.match(study, /Cargo disputado \/ eleição/);
  assert.match(study, /Situação naquele pleito/);
  assert.match(study, /classifyElectionOutcome\(vote\.situation\)/);
  assert.match(study, /latestElectionYear/);
  assert.match(study, /identificadores oficiais/);
});
