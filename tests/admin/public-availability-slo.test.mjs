import assert from "node:assert/strict";
import test from "node:test";

const module = await import(
  "../../apps/admin/app/public-availability-slo.mjs"
).catch(() => null);

test("traduz o gate sintético sem alegar que observa todo o tráfego", () => {
  assert.ok(module?.formatPublicAvailabilitySlo, "formatador ainda não implementado");
  const result = module.formatPublicAvailabilitySlo({
    availability_success_streak_days: 2,
    availability_days_observed: 3,
    availability_latest_probe_at: "2026-09-04T23:17:00Z",
    availability_expected_runs_per_day: 20,
    availability_daily_history: [
      {
        day: "2026-09-03",
        state: "passed",
        runs_observed: 24,
        valid_runs: 24,
        http_5xx_count: 0,
      },
      {
        day: "2026-09-02",
        state: "passed",
        runs_observed: 23,
        valid_runs: 23,
        http_5xx_count: 0,
      },
      {
        day: "2026-09-01",
        state: "incomplete",
        runs_observed: 12,
        valid_runs: 12,
        http_5xx_count: 0,
      },
    ],
  });

  assert.deepEqual(result, {
    progress: "2 de 7 dias encerrados aprovados em sequência",
    percent: 28.57,
    ready: false,
    note:
      "Ainda faltam 5 dias consecutivos aprovados. Cada dia exige pelo menos 20 sondagens agendadas das rotas públicas críticas.",
    limitation:
      "A sondagem verifica rotas públicas em intervalos regulares; não observa todas as requisições de visitantes nem substitui os logs da Vercel.",
    history: [
      {
        day: "2026-09-03",
        label: "Aprovado",
        detail: "24 de 20 sondagens mínimas · nenhum HTTP 5xx",
        tone: "healthy",
      },
      {
        day: "2026-09-02",
        label: "Aprovado",
        detail: "23 de 20 sondagens mínimas · nenhum HTTP 5xx",
        tone: "healthy",
      },
      {
        day: "2026-09-01",
        label: "Cobertura insuficiente",
        detail: "12 de 20 sondagens mínimas · nenhum HTTP 5xx",
        tone: "attention",
      },
    ],
  });
});

test("um 5xx interrompe a sequência e permanece visível no histórico", () => {
  assert.ok(module?.formatPublicAvailabilitySlo, "formatador ainda não implementado");
  const result = module.formatPublicAvailabilitySlo({
    availability_success_streak_days: 0,
    availability_days_observed: 1,
    availability_latest_probe_at: "2026-09-04T23:17:00Z",
    availability_expected_runs_per_day: 20,
    availability_daily_history: [
      {
        day: "2026-09-03",
        state: "failed",
        runs_observed: 24,
        valid_runs: 23,
        http_5xx_count: 1,
      },
    ],
  });

  assert.equal(result.progress, "0 de 7 dias encerrados aprovados em sequência");
  assert.deepEqual(result.history[0], {
    day: "2026-09-03",
    label: "Falhou",
    detail: "24 de 20 sondagens mínimas · 1 resposta HTTP 5xx",
    tone: "failed",
  });
});

test("recusa histórico incoerente em vez de inventar progresso", () => {
  assert.ok(module?.formatPublicAvailabilitySlo, "formatador ainda não implementado");
  assert.equal(
    module.formatPublicAvailabilitySlo({
      availability_success_streak_days: 7,
      availability_days_observed: 1,
      availability_latest_probe_at: null,
      availability_expected_runs_per_day: 0,
      availability_daily_history: [],
    }),
    null,
  );
});

test("reconcilia a sequência declarada com dias e contagens reais", () => {
  const day = { day: "2026-09-03", state: "passed", runs_observed: 20, valid_runs: 20, http_5xx_count: 0 };
  const baseline = {
    availability_success_streak_days: 1,
    availability_days_observed: 1,
    availability_expected_runs_per_day: 20,
    availability_daily_history: [day],
  };
  assert.ok(module.formatPublicAvailabilitySlo(baseline));
  for (const invalid of [
    { ...baseline, availability_success_streak_days: 7, availability_days_observed: 7, availability_daily_history: [] },
    { ...baseline, availability_success_streak_days: 0 },
    { ...baseline, availability_days_observed: 2 },
    { ...baseline, availability_daily_history: [{ ...day, valid_runs: 0 }] },
    { ...baseline, availability_daily_history: [{ ...day, http_5xx_count: 1 }] },
    { ...baseline, availability_daily_history: [{ ...day, day: "2026-02-30" }] },
    { ...baseline, availability_daily_history: [day, day] },
    { ...baseline, availability_daily_history: [day, { ...day, day: "2026-09-01" }] },
  ]) {
    assert.equal(module.formatPublicAvailabilitySlo(invalid), null, JSON.stringify(invalid));
  }
});
