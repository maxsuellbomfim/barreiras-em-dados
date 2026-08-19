const SHA256 = /^[0-9a-f]{64}$/;
const CNPJ = /^\d{14}$/;
const REGISTRIES = new Set(["ceis", "cnep"]);
const METHODOLOGY = "supplier-sanctions/1.0.0";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null || value === undefined ? null : requiredText(value);
}

function parseSanctionRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const registry = requiredText(row.registry);
  const sanctionId = requiredText(row.sanction_id);
  const supplierCnpj = requiredText(row.supplier_cnpj);
  const sanctionedName = requiredText(row.sanctioned_name);
  const apiSourceUrl = requiredText(row.api_source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  const legalBasisCodes = Array.isArray(row.legal_basis_codes)
    ? row.legal_basis_codes.filter((code) => typeof code === "string")
    : null;
  if (
    !registry || !REGISTRIES.has(registry) || !sanctionId ||
    // A projeção só publica pessoa jurídica; qualquer documento fora do CNPJ
    // de 14 dígitos invalida o lote inteiro no navegador também.
    !supplierCnpj || !CNPJ.test(supplierCnpj) ||
    !sanctionedName || legalBasisCodes === null ||
    !apiSourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) ||
    !collectedAt || !Number.isFinite(Date.parse(collectedAt)) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    sanctionRecordId: requiredText(row.sanction_record_id),
    registry,
    sanctionId,
    supplierCnpj,
    sanctionedName,
    companyName: optionalText(row.company_name),
    sanctionType: optionalText(row.sanction_type),
    sanctioningBody: optionalText(row.sanctioning_body),
    sanctioningBodySphere: optionalText(row.sanctioning_body_sphere),
    sanctioningBodyUf: optionalText(row.sanctioning_body_uf),
    sanctionSource: optionalText(row.sanction_source),
    processNumber: optionalText(row.process_number),
    startDateText: optionalText(row.start_date_text),
    endDateText: optionalText(row.end_date_text),
    publicationDateText: optionalText(row.publication_date_text),
    referenceDateText: optionalText(row.reference_date_text),
    legalBasisCodes,
    apiSourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseSupplierSanctionRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseSanctionRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function formatSanctionCnpj(cnpj) {
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
}

export function sanctionRegistryLabel(registry) {
  return registry === "ceis"
    ? "CEIS — Empresas Inidôneas e Suspensas"
    : "CNEP — Empresas Punidas (Lei Anticorrupção)";
}
