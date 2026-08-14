/**
 * Traduz somente estados determinísticos produzidos pela reconciliação SQL.
 * Não calcula valores financeiros nem infere execução.
 *
 * @param {{
 *   executionStatus: "execution_confirmed" | "ambiguous_official_key" |
 *     "not_found_in_execution_source" | "official_link_key_unavailable" |
 *     "scope_not_available",
 *   loaScopeOccurrences: number,
 *   executionOccurrences: number,
 *   paidAmount: string | null,
 * }} record
 */
export function stateLoaExecutionStatusCopy(record) {
  if (record.executionStatus === "execution_confirmed") {
    return {
      tone: "confirmed",
      label: "Execução encontrada",
      explanation:
        "A autorização foi ligada a uma única linha da execução estadual. Valores de R$ 0,00 são os publicados pela própria fonte neste retrato, não campos ausentes.",
    };
  }
  if (record.executionStatus === "ambiguous_official_key") {
    return {
      tone: "pending",
      label: "Ligação ambígua",
      explanation:
        `A mesma chave aparece ${record.loaScopeOccurrences} vez${record.loaScopeOccurrences === 1 ? "" : "es"} na LOA e ${record.executionOccurrences} vez${record.executionOccurrences === 1 ? "" : "es"} na execução. Não atribuímos empenho, liquidação ou pagamento a esta emenda sem uma chave oficial exclusiva.`,
    };
  }
  if (record.executionStatus === "not_found_in_execution_source") {
    return {
      tone: "not-found",
      label: "Não encontrada na execução consultada",
      explanation:
        "A autorização consta na LOA, mas nenhuma linha correspondente foi localizada no retrato estadual consultado. Isso não significa pagamento zero nem ausência definitiva.",
    };
  }
  if (record.executionStatus === "official_link_key_unavailable") {
    return {
      tone: "unavailable",
      label: "Fonte sem chave para o cruzamento",
      explanation:
        "Nos documentos oficiais deste ano, não encontramos os identificadores necessários para ligar cada autorização a uma linha exclusiva da execução. Por isso, não atribuímos empenho, liquidação ou pagamento. Isso não significa valor zero.",
    };
  }
  return {
    tone: "unavailable",
    label: "Cruzamento ainda indisponível",
    explanation:
      "Este exercício ainda não possui índice estadual completo para uma ligação segura. A autorização continua visível, mas os estágios de execução permanecem sem atribuição.",
  };
}
