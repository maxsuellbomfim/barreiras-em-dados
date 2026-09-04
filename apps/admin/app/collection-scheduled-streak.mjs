const TARGET_RUNS = 7;

function isCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export function formatScheduledRunStreak(item) {
  const streak = item.scheduled_success_streak;
  const observed = item.scheduled_runs_observed;

  if (
    !isCount(streak) ||
    !isCount(observed) ||
    streak > observed ||
    streak > TARGET_RUNS ||
    observed > TARGET_RUNS
  ) {
    return null;
  }

  const remaining = TARGET_RUNS - streak;
  return {
    progress: `${streak.toLocaleString("pt-BR")} de ${TARGET_RUNS} execuções consecutivas válidas`,
    note:
      observed === 0
        ? "Aguardando a primeira execução identificada do Agendador do Windows."
        : remaining === 0
          ? "Gate operacional comprovado pelas sete execuções agendadas mais recentes."
          : `A medição começou quando a origem das execuções passou a ser registrada. Ainda faltam ${remaining.toLocaleString("pt-BR")} execuções válidas consecutivas.`,
    percent: Number(((streak / TARGET_RUNS) * 100).toFixed(2)),
    ready: remaining === 0,
  };
}
