// Indícios publicados após revisão automatizada registrada (ADR 0099,
// public-indicios/1.0.0). Indício não é prova: a página mostra o fato, a
// regra e a fonte. Valores chegam como decimal em texto; nenhuma conta aqui.
const METHODOLOGIES = new Set(["public-indicios/1.0.0"]);
const RULES = new Set(["supplier-recent-opening"]);
const REVIEW_KINDS = new Set(["human", "automated"]);
const SEVERITIES = new Set(["information", "low", "medium", "high"]);
const DECIMAL = /^\d+(\.\d{1,2})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const CNPJ = /^\d{14}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function decimal(value) {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return value.toFixed(2);
  }
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function isoDate(value) {
  return typeof value === "string" && ISO_DATE.test(value) ? value : null;
}

/**
 * Linha inválida derruba o conjunto: indício pela metade não é publicado.
 * Lista vazia é resultado válido (nenhum indício aprovado).
 */
export function parseIndicioRows(rows) {
  if (!Array.isArray(rows)) return null;
  const items = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const item = {
      findingId: text(row.finding_id),
      ruleSlug: text(row.rule_slug),
      ruleName: text(row.rule_name),
      ruleDescription: text(row.rule_description),
      ruleMethodology: text(row.rule_methodology),
      severity: text(row.severity),
      publicExplanation: text(row.public_explanation),
      reviewRationale: text(row.review_rationale),
      reviewKind: text(row.review_kind),
      reviewedAt: text(row.reviewed_at),
      supplierName: text(row.supplier_name),
      supplierCnpj: text(row.supplier_cnpj),
      contractNumber: text(row.contract_number),
      contractObject: text(row.contract_object),
      contractValue: decimal(row.contract_value),
      contractStart: isoDate(row.contract_start),
      openedOn: isoDate(row.opened_on),
      daysAfterOpening: Number.isSafeInteger(row.days_after_opening) && row.days_after_opening >= 0
        ? row.days_after_opening : null,
      amendmentsValue: row.amendments_value === null ? null : decimal(row.amendments_value),
      contractSourceUrl: text(row.contract_source_url),
      contractArtifactSha256: text(row.contract_artifact_sha256),
      registryArtifactSha256: text(row.registry_artifact_sha256),
    };
    if (
      item.findingId === null ||
      !RULES.has(item.ruleSlug) ||
      item.ruleName === null ||
      item.ruleDescription === null ||
      item.ruleMethodology === null ||
      !SEVERITIES.has(item.severity) ||
      item.publicExplanation === null ||
      item.reviewRationale === null ||
      !REVIEW_KINDS.has(item.reviewKind) ||
      item.reviewedAt === null ||
      item.supplierName === null ||
      !CNPJ.test(item.supplierCnpj ?? "") ||
      item.contractNumber === null ||
      item.contractValue === null ||
      item.contractStart === null ||
      item.openedOn === null ||
      item.daysAfterOpening === null ||
      (row.amendments_value !== null && item.amendmentsValue === null) ||
      (item.contractSourceUrl !== null && !item.contractSourceUrl.startsWith("https://")) ||
      !SHA256.test(item.contractArtifactSha256 ?? "") ||
      !SHA256.test(item.registryArtifactSha256 ?? "") ||
      !METHODOLOGIES.has(row.methodology_version)
    ) {
      return null;
    }
    items.push(item);
  }
  return items;
}

/** CNPJ é público; a máscara só ajuda a ler. */
export function formatCnpj(cnpj) {
  return cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

export async function getPublicIndicios() {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_indicios`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ page_size: 200 }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const items = parseIndicioRows(await response.json());
    return items === null ? { state: "unavailable" } : { state: "available", items };
  } catch {
    return { state: "unavailable" };
  }
}
