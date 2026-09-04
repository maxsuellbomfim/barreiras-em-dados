function isCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function itemLabel(value) {
  return value === 1 ? "item" : "itens";
}

function documentLabel(value) {
  return value === 1 ? "documento" : "documentos";
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

  if (item.latest_work_unit === "document") {
    return {
      heading: "Progresso documental",
      completed: `${completed.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")} documentos preservados`,
      remaining:
        remaining === 0
          ? "Todos os documentos foram preservados"
          : `${remaining.toLocaleString("pt-BR")} ${documentLabel(remaining)} ainda aguard${remaining === 1 ? "a" : "am"} preservação`,
      latestBatch: `Último lote: ${latestBatch.toLocaleString("pt-BR")} ${documentLabel(latestBatch)}`,
      percent: Number(((completed / total) * 100).toFixed(2)),
    };
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
