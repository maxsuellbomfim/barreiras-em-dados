const MISSING_COVERAGE_PATTERNS = Object.freeze([
  /relatorios? comparaveis (?:ainda )?nao (?:esta|estao) disponiveis/,
  /(?:aguarda|aguardando)[^.!?]{0,80}relatorios?/,
  /(?:falta|faltam)[^.!?]{0,40}(?:dados|relatorios?|cobertura)/,
  /(?:dados|relatorios?)[^.!?]{0,40}(?:ainda )?nao disponiveis/,
  /dados parciais/,
  /cobertura (?:ainda )?(?:incompleta|indisponivel)/,
]);

function normalizeForComparison(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/\s+/g, " ")
    .trim();
}

export function isMonthlyFinanceCommentaryCompatible(status, commentary) {
  if (status !== "operational") return true;
  const normalized = normalizeForComparison(commentary);
  return !MISSING_COVERAGE_PATTERNS.some((pattern) => pattern.test(normalized));
}
