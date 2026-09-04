import assert from "node:assert/strict";
import test from "node:test";

import { formatScheduledRunStreak } from "../../apps/admin/app/collection-scheduled-streak.mjs";

test("explica uma sequência agendada ainda em formação", () => {
  assert.deepEqual(
    formatScheduledRunStreak({
      scheduled_success_streak: 3,
      scheduled_runs_observed: 3,
      latest_scheduled_run_at: "2026-09-04T13:30:00Z",
    }),
    {
      progress: "3 de 7 execuções consecutivas válidas",
      note: "A medição começou quando a origem das execuções passou a ser registrada. Ainda faltam 4 execuções válidas consecutivas.",
      percent: 42.86,
      ready: false,
    },
  );
});

test("não inventa histórico anterior à instrumentação", () => {
  assert.deepEqual(
    formatScheduledRunStreak({
      scheduled_success_streak: 0,
      scheduled_runs_observed: 0,
      latest_scheduled_run_at: null,
    }),
    {
      progress: "0 de 7 execuções consecutivas válidas",
      note: "Aguardando a primeira execução identificada do Agendador do Windows.",
      percent: 0,
      ready: false,
    },
  );
});

test("fecha o gate após sete execuções válidas", () => {
  assert.equal(
    formatScheduledRunStreak({
      scheduled_success_streak: 7,
      scheduled_runs_observed: 7,
      latest_scheduled_run_at: "2026-09-04T15:00:00Z",
    })?.ready,
    true,
  );
});

test("falha fechado para contadores incoerentes", () => {
  assert.equal(
    formatScheduledRunStreak({
      scheduled_success_streak: 5,
      scheduled_runs_observed: 3,
      latest_scheduled_run_at: "2026-09-04T15:00:00Z",
    }),
    null,
  );
});
