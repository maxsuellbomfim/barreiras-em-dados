import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const workflow = await readFile(new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url), "utf8");
const job = workflow.slice(workflow.indexOf("  transferegov:"), workflow.indexOf("  siconfi_dca:"));
const steps = job.split(/\n      - name: /).slice(1);
const step = (name) => {
  const result = steps.find((value) => value.startsWith(`${name}\n`) || value.startsWith(`${name}\r\n`));
  assert.ok(result, `etapa ausente: ${name}`);
  return result;
};

test("403 histórico não impede preparar a evidência das fontes federais independentes", () => {
  assert.match(step("Verificar CA oficial do Supabase"), /id: federal_preflight/);
  const evidence = step("Iniciar evidência da execução federal");
  assert.match(evidence, /id: federal_evidence/);
  assert.match(evidence, /if: \$\{\{ !cancelled\(\) && steps\.federal_preflight\.outcome == 'success' \}\}/);
  assert.match(evidence, /date -u/);
  assert.match(evidence, /: > "\$RUNNER_TEMP\/federal-collector\.log"/);
});

test("cada fonte corrente e seu gate continuam após falha independente, mas nunca após cancelamento ou preflight falho", () => {
  for (const name of [
    "Preservar execução federal de emendas em Barreiras",
    "Preservar documentos anuais das emendas federais",
    "Preservar retrato do Transferegov",
    "Confirmar publicação das fontes federais",
  ]) {
    assert.match(step(name), /if: \$\{\{ !cancelled\(\) && steps\.federal_evidence\.outcome == 'success' \}\}/, name);
  }
  // Failure must remain a failed job, not a green result with hidden errors.
  assert.doesNotMatch(job, /^\s*continue-on-error:|\|\| true/m);
  assert.match(step("Confirmar publicação das fontes federais"), /--collector-log[\s\S]*--not-before-file/);
});

test("condições do workflow mantêm a fonte seguinte habilitada após 403 e bloqueiam execução sem preparo", () => {
  const evidence = step("Iniciar evidência da execução federal").match(/if: \$\{\{ (.+) \}\}/)?.[1];
  const current = step("Preservar retrato do Transferegov").match(/if: \$\{\{ (.+) \}\}/)?.[1];
  assert.ok(evidence && current);
  for (const [preflight, ready, cancelled, expectedEvidence, expectedCurrent] of [
    ["success", "success", false, true, true],
    ["failure", "skipped", false, false, false],
    ["skipped", "skipped", false, false, false],
    ["success", "failure", false, true, false],
    ["success", "success", true, false, false],
  ]) {
    const context = {
      cancelled: () => cancelled,
      steps: {
        federal_preflight: { outcome: preflight },
        federal_evidence: { outcome: ready },
        historical_catalog: { outcome: "failure" },
        cgu_execution: { outcome: "failure" },
      },
    };
    assert.equal(runInNewContext(evidence, context), expectedEvidence);
    assert.equal(runInNewContext(current, context), expectedCurrent);
  }
});
