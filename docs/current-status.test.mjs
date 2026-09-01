import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("documentos de entrada apontam para um único estado atual", async () => {
  const [readme, claude, plan, current] = await Promise.all([
    readFile(new URL("README.md", root), "utf8"),
    readFile(new URL("CLAUDE.md", root), "utf8"),
    readFile(new URL("docs/DEVELOPMENT_PLAN.md", root), "utf8"),
    readFile(new URL("docs/CURRENT_STATUS.md", root), "utf8"),
  ]);

  assert.match(readme, /docs\/CURRENT_STATUS\.md/);
  assert.match(claude, /docs\/CURRENT_STATUS\.md/);
  assert.match(plan, /docs\/CURRENT_STATUS\.md/);
  assert.match(current, /31\/08\/2026/);
  assert.doesNotMatch(readme, /Este repositório está na etapa 1A/);
  assert.doesNotMatch(plan, /etapa zero/i);
  assert.doesNotMatch(
    claude,
    /As etapas ativas são \*\*1B\/1C[^\n]+início da \*\*Etapa 2/,
  );
});

test("instruções para agentes são curtas e executáveis", async () => {
  const agents = await readFile(new URL("AGENTS.md", root), "utf8");

  assert.ok(agents.length < 6_000, "AGENTS.md deve preservar o orçamento de contexto");
  assert.match(agents, /menor fluxo vertical/i);
  assert.match(agents, /não leia todas as\s+migrations/i);
  assert.match(agents, /teste[\s\S]{0,80}falhar/i);
  assert.match(agents, /docs\/CURRENT_STATUS\.md/);
});
