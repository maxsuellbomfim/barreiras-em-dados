function formatDate(value) {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export function formatBackfillProgress(item) {
  if (
    !item.backfill_horizon ||
    !item.continuous_coverage_start ||
    !item.continuous_coverage_end ||
    item.backfill_classified_days === null ||
    item.backfill_total_days === null ||
    item.backfill_progress_percent === null
  ) {
    return null;
  }

  const nextWindow =
    item.next_backfill_start && item.next_backfill_end
      ? `${formatDate(item.next_backfill_start)} a ${formatDate(item.next_backfill_end)}`
      : "Retroatividade concluída";

  return {
    coverage: `${formatDate(item.continuous_coverage_start)} a ${formatDate(item.continuous_coverage_end)}`,
    nextWindow,
    progress: `${item.backfill_classified_days.toLocaleString("pt-BR")} de ${item.backfill_total_days.toLocaleString("pt-BR")} dias contínuos (${item.backfill_progress_percent.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%)`,
    horizon: formatDate(item.backfill_horizon),
  };
}
