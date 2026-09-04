import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/ci.yml", import.meta.url),
  "utf8",
);

test("Verificações agenda somente a sondagem pública leve a cada hora", () => {
  assert.match(workflow, /workflow_dispatch:/);
  assert.match(workflow, /schedule:\s*\n\s*- cron: ["']17 \* \* \* \*["']/);
  assert.match(workflow, /public_availability:\s*\n\s*name: Sondar rotas públicas críticas/);
  assert.match(
    workflow,
    /if: github\.event_name == 'schedule' \|\| github\.event_name == 'workflow_dispatch'/,
  );
  assert.match(workflow, /probe_public_availability/);
  assert.match(workflow, /--execution-origin github_actions/);
  assert.match(workflow, /WORKFLOW_EVENT: \$\{\{ github\.event_name \}\}/);
  assert.match(workflow, /--workflow-event "\$WORKFLOW_EVENT"/);
  assert.match(workflow, /PUBLIC_SITE_BASE_URL: https:\/\/barreiras-em-dados\.vercel\.app/);
  assert.match(workflow, /DATABASE_URL: \$\{\{ secrets\.QUERIDO_DIARIO_DATABASE_URL \}\}/);

  const nodeJob = workflow.match(/\n  node:\n[\s\S]*?(?=\n  [a-z_]+:\n)/)?.[0] ?? "";
  const pythonJob = workflow.match(/\n  python:\n[\s\S]*?(?=\n  [a-z_]+:\n)/)?.[0] ?? "";
  assert.match(nodeJob, /if: github\.event_name == 'pull_request' \|\| github\.event_name == 'push'/);
  assert.match(pythonJob, /if: github\.event_name == 'pull_request' \|\| github\.event_name == 'push'/);
});
