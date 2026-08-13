const MUNICIPAL_OFFICES = new Set(["prefeito", "vice-prefeito", "vereador"]);
const GENERAL_OFFICES = new Set([
  "governador",
  "vice-governador",
  "senador",
  "deputado estadual",
  "deputado federal",
]);

function normalized(value) {
  return typeof value === "string"
    ? value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toLocaleLowerCase("pt-BR")
    : "";
}

export function classifyElectionOutcome(situation) {
  const value = normalized(situation);
  if (!value) return "unknown";
  if (value === "nao eleito") return "not_elected";
  if (value === "suplente") return "alternate";
  if (value === "eleito" || value.startsWith("eleito por ")) return "elected";
  return "other";
}

export function outcomeLabel(outcome) {
  switch (outcome) {
    case "elected":
      return "Eleito naquele pleito";
    case "alternate":
      return "Suplente naquele pleito";
    case "not_elected":
      return "Não eleito naquele pleito";
    case "other":
      return "Outra situação no pleito";
    default:
      return "Situação não informada";
  }
}

export function electionCycleLabel(electionYear, office) {
  const normalizedOffice = normalized(office);
  if (MUNICIPAL_OFFICES.has(normalizedOffice)) {
    return `Eleição municipal de ${electionYear}`;
  }
  if (GENERAL_OFFICES.has(normalizedOffice)) {
    return `Eleição geral de ${electionYear}`;
  }
  return `Eleição de ${electionYear}`;
}

export function electionPeriodLabel(electionYear, office) {
  if (!Number.isSafeInteger(electionYear)) return "período decorrente do pleito";
  const normalizedOffice = normalized(office);
  const startYear = electionYear + 1;
  if (normalizedOffice === "senador") {
    return `ciclo ${startYear}–${startYear + 8}`;
  }
  if (
    MUNICIPAL_OFFICES.has(normalizedOffice)
    || normalizedOffice === "governador"
    || normalizedOffice === "vice-governador"
  ) {
    return `ciclo ${startYear}–${startYear + 3}`;
  }
  if (GENERAL_OFFICES.has(normalizedOffice)) {
    return `ciclo ${startYear}–${startYear + 4}`;
  }
  return "período decorrente do pleito";
}

export function latestElectionYear(years) {
  const validYears = years.filter(Number.isSafeInteger);
  return validYears.length > 0 ? String(Math.max(...validYears)) : "todos";
}
