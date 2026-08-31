function isCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function itemLabel(value) {
  return value === 1 ? "item" : "itens";
}

export function formatCollectionWorkProgress(item) {
  const completed = item.latest_work_completed;
  const total = item.latest_work_total;
  const remaining = item.latest_work_remaining;
  const latestBatch = item.latest_batch_processed;

  if (
    !isCount(completed) ||
    !isCount(total) ||
    !isCount(remaining) ||
    !isCount(latestBatch) ||
    total === 0 ||
    completed + remaining !== total ||
    latestBatch > completed
  ) {
    return null;
  }

  return {
    completed: `${completed.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")} itens concluídos`,
    remaining:
      remaining === 0
        ? "Ciclo integralmente concluído"
        : `${remaining.toLocaleString("pt-BR")} ${itemLabel(remaining)} ainda aguard${remaining === 1 ? "a" : "am"} coleta`,
    latestBatch: `Último lote: ${latestBatch.toLocaleString("pt-BR")} ${itemLabel(latestBatch)}`,
    percent: Number(((completed / total) * 100).toFixed(2)),
  };
}
