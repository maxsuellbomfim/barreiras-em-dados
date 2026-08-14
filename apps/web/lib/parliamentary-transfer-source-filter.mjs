const SOURCES = new Set([
  "legislaturas",
  "federal-atual",
  "federal-historico",
  "estadual",
]);

/**
 * Mantém as séries oficiais visivelmente separadas. Entradas múltiplas ou fora
 * da lista fechada retornam para a fonte federal atual, que é o recorte padrão.
 *
 * @param {string | readonly string[] | undefined} requestedSource
 */
export function resolveTransferSourceSelection(requestedSource) {
  const source = typeof requestedSource === "string" && SOURCES.has(requestedSource)
    ? requestedSource
    : "federal-atual";

  return {
    source,
    showLegislatures: source === "legislaturas",
    showCurrentFederal: source === "federal-atual",
    showHistoricalFederal: source === "federal-historico",
    showState: source === "estadual",
  };
}
