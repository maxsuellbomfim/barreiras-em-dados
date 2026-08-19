const SHA256 = /^[0-9a-f]{64}$/;
const METHODOLOGY = "municipal-procurement-processes/1.0.0";

// Legenda oficial dos códigos de modalidade e categoria, capturada em
// 19/08/2026 do filtro público do próprio portal da transparência municipal
// (portaldatransparencia.barreiras.ba.gov.br/licitacoes). A API publica só o
// código; um código fora desta legenda é exibido literalmente como código.
// Situação e resultado NÃO têm legenda publicada pela fonte e permanecem
// sempre como código literal.
const MODALITY_LEGEND = {
  1: "Dispensa",
  2: "Tomada de Preços",
  3: "Convite",
  4: "Inexibilidade",
  5: "Concorrência",
  6: "Pregão Presencial",
  7: "Leilão",
  8: "Concurso",
  9: "Pregão Eletrônico",
  10: "Chamada Pública",
  11: "Credenciamento Público",
  12: "Dispensa Covid-19",
  13: "Contratação direta",
  14: "Inexibilidade Covid-19",
  15: "Pregão Presencial Covid-19",
  16: "Dispensa - Lei 14.133/21",
  17: "Dispensa eletrônica",
};
const CATEGORY_LEGEND = {
  1: "Transporte Escolar",
  2: "Material de consumo",
  3: "Material Permanente",
  4: "Material Distribuição Gratuita",
  5: "Serviços Comuns",
  6: "Serviços Técnicos",
  7: "Serviços de Engenharia",
  8: "Obras e Instalações",
  9: "Merenda Escolar",
};

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null || value === undefined ? null : requiredText(value);
}

function parseProcessRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const processRecordId = requiredText(row.process_record_id);
  const processNumber = requiredText(row.process_number);
  const processObject = requiredText(row.process_object);
  const apiSourceUrl = requiredText(row.api_source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  if (
    !processRecordId || !processNumber || !processObject ||
    !apiSourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) ||
    !collectedAt || !Number.isFinite(Date.parse(collectedAt)) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    processRecordId,
    sourceProcessId: optionalText(row.source_process_id),
    processNumber,
    noticeNumber: optionalText(row.notice_number),
    publicationDateText: optionalText(row.publication_date_text),
    openingDateText: optionalText(row.opening_date_text),
    processObject,
    biddingTypeCode: optionalText(row.bidding_type_code),
    modalityCode: optionalText(row.modality_code),
    categoryCode: optionalText(row.category_code),
    situationCode: optionalText(row.situation_code),
    resultCode: optionalText(row.result_code),
    estimatedValueText: optionalText(row.estimated_value_text),
    awardedValueText: optionalText(row.awarded_value_text),
    apiSourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseMunicipalProcurementProcessRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseProcessRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function municipalModalityLabel(code) {
  if (code === null) return "não informada na fonte";
  const label = MODALITY_LEGEND[Number.parseInt(code, 10)];
  return label
    ? `${label} (código ${code} da fonte)`
    : `código ${code} (sem legenda publicada pela fonte)`;
}

export function municipalCategoryLabel(code) {
  if (code === null) return "não informada na fonte";
  const label = CATEGORY_LEGEND[Number.parseInt(code, 10)];
  return label
    ? `${label} (código ${code} da fonte)`
    : `código ${code} (sem legenda publicada pela fonte)`;
}

export function municipalSourceCodeLabel(code) {
  if (code === null) return "não informado na fonte";
  return `código ${code} (a fonte não publica legenda)`;
}
