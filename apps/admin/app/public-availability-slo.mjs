const TARGET_DAYS = 7;

function isCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function historyItem(value, expectedRuns) {
  if (
    !value ||
    typeof value !== "object" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value.day) ||
    !["passed", "failed", "incomplete", "missing"].includes(value.state) ||
    !isCount(value.runs_observed) ||
    !isCount(value.valid_runs) ||
    !isCount(value.http_5xx_count) ||
    value.valid_runs > value.runs_observed
  ) {
    return null;
  }
  const status = {
    passed: ["Aprovado", "healthy"],
    failed: ["Falhou", "failed"],
    incomplete: ["Cobertura insuficiente", "attention"],
    missing: ["Sem sondagem", "unknown"],
  }[value.state];
  const fiveXx = value.http_5xx_count === 0
    ? "nenhum HTTP 5xx"
    : `${value.http_5xx_count.toLocaleString("pt-BR")} resposta${value.http_5xx_count === 1 ? "" : "s"} HTTP 5xx`;
  return {
    day: value.day,
    label: status[0],
    detail: `${value.runs_observed.toLocaleString("pt-BR")} de ${expectedRuns.toLocaleString("pt-BR")} sondagens mínimas · ${fiveXx}`,
    tone: status[1],
  };
}

export function formatPublicAvailabilitySlo(item) {
  const streak = item.availability_success_streak_days;
  const observed = item.availability_days_observed;
  const expectedRuns = item.availability_expected_runs_per_day;
  const rawHistory = item.availability_daily_history;
  if (
    !isCount(streak) ||
    !isCount(observed) ||
    !isCount(expectedRuns) ||
    expectedRuns < 1 ||
    streak > TARGET_DAYS ||
    streak > observed ||
    observed > TARGET_DAYS ||
    !Array.isArray(rawHistory) ||
    rawHistory.length > TARGET_DAYS
  ) {
    return null;
  }
  const history = rawHistory.map((value) => historyItem(value, expectedRuns));
  if (history.some((value) => value === null)) return null;
  const remaining = TARGET_DAYS - streak;
  return {
    progress: `${streak.toLocaleString("pt-BR")} de ${TARGET_DAYS} dias encerrados aprovados em sequência`,
    percent: Number(((streak / TARGET_DAYS) * 100).toFixed(2)),
    ready: remaining === 0,
    note:
      remaining === 0
        ? "Gate sintético comprovado pelos sete dias encerrados mais recentes."
        : `Ainda faltam ${remaining.toLocaleString("pt-BR")} dias consecutivos aprovados. Cada dia exige pelo menos ${expectedRuns.toLocaleString("pt-BR")} sondagens agendadas das rotas públicas críticas.`,
    limitation:
      "A sondagem verifica rotas públicas em intervalos regulares; não observa todas as requisições de visitantes nem substitui os logs da Vercel.",
    history,
  };
}
