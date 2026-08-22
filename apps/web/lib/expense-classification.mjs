export const EXPENSE_CLASSIFICATION_SOURCE_URL =
  "https://cdn.tesouro.gov.br/sistemas-internos/apex/producao/sistemas/thot/arquivos/publicacoes/26316_927376/anexos/2057_97083/Anexos%203%20ed.pdf";

const OFFICIAL_LABELS = new Map([
  ["3.1.9.0.04.00.00", "Contratação por Tempo Determinado"],
  ["3.1.9.0.11.00.00", "Vencimentos e Vantagens Fixas - Pessoal Civil"],
  ["3.3.9.0.30.00.00", "Material de Consumo"],
  [
    "3.3.9.0.32.00.00",
    "Material, Bem ou Serviço para Distribuição Gratuita",
  ],
  ["3.3.9.0.39.00.00", "Outros Serviços de Terceiros - Pessoa Jurídica"],
  ["3.3.9.0.47.00.00", "Obrigações Tributárias e Contributivas"],
  [
    "3.1.9.0.96.00.00",
    "Ressarcimento de Despesas de Pessoal Requisitado",
  ],
  ["3.2.9.0.21.00.00", "Juros sobre a Dívida por Contrato"],
  ["3.2.9.0.22.00.00", "Outros Encargos sobre a Dívida por Contrato"],
  [
    "3.3.9.0.95.00.00",
    "Indenização pela Execução de Trabalhos de Campo",
  ],
  ["4.4.9.0.39.00.00", "Outros Serviços de Terceiros - Pessoa Jurídica"],
  ["4.6.9.0.71.00.00", "Principal da Dívida Contratual Resgatado"],
  [
    "4.6.9.0.75.00.00",
    "Correção Monetária da Dívida de Operações de Crédito por Antecipação da Receita",
  ],
]);

function comparable(value) {
  const stopWords = new Set(["a", "as", "da", "das", "de", "do", "dos", "e"]);
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((token) => token && !stopWords.has(token))
    .join(" ");
}

export function classifyExpenseDescription(expenseCode, sourceDescription) {
  const literal = typeof sourceDescription === "string"
    ? sourceDescription.trim()
    : "";
  const official = OFFICIAL_LABELS.get(expenseCode);
  if (!official) {
    return {
      displayDescription: literal,
      sourceDescription: literal,
      sourceWasTruncated: false,
      classificationStatus: "source_only",
    };
  }

  const sourceComparable = comparable(literal);
  const officialComparable = comparable(official);
  if (sourceComparable === officialComparable) {
    return {
      displayDescription: official,
      sourceDescription: literal,
      sourceWasTruncated: false,
      classificationStatus: "official_code_match",
    };
  }
  if (sourceComparable.length > 0 && officialComparable.startsWith(sourceComparable)) {
    return {
      displayDescription: official,
      sourceDescription: literal,
      sourceWasTruncated: true,
      classificationStatus: "official_code_match",
    };
  }
  return {
    displayDescription: literal,
    sourceDescription: literal,
    sourceWasTruncated: false,
    classificationStatus: "source_conflict",
  };
}
