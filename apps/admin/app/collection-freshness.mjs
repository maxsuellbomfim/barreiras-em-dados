function totalPolicyHours(item) {
  if (item.freshness_expected_hours === null) return null;
  return item.freshness_expected_hours + item.freshness_grace_hours;
}

export function formatFreshnessPolicy(item) {
  const hours = totalPolicyHours(item);
  if (hours === null) return "Sem prazo operacional contínuo";
  return `Até ${hours.toLocaleString("pt-BR")} horas entre atualizações válidas`;
}

export function formatFreshnessStatus(item) {
  if (item.freshness_status === "current") {
    return "Atualização dentro do prazo";
  }
  if (item.freshness_status === "overdue") {
    const hours = item.freshness_overdue_hours ?? 0;
    return `Atualização atrasada há cerca de ${hours.toLocaleString("pt-BR")} horas`;
  }
  if (item.freshness_status === "never_updated") {
    return "Nenhuma atualização válida registrada";
  }
  return "Sem prazo contínuo definido";
}

export function freshnessRequiresAttention(item) {
  return (
    item.freshness_status === "overdue" ||
    item.freshness_status === "never_updated"
  );
}
