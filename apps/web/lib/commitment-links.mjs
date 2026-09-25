const SHA256 = /^[0-9a-f]{64}$/;
const COMMITMENT_KEY = /^O-\d+$/;
const DATE_TEXT = /^\d{2}\/\d{2}\/\d{4}$/;
const METHODOLOGY = "commitment-contract-links/1.0.0";
const RULE = /^commitment-contract-link\/\d+\.\d+\.\d+$/;
const REVIEW_MODES = new Set(["automated", "human"]);

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseLinkRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const link = {
    linkId: text(row.link_id),
    contractPortalId: text(row.contract_portal_id),
    commitmentKey: text(row.commitment_key),
    commitmentNumber: text(row.commitment_number),
    issueDateText: text(row.issue_date_text),
    publicBody: text(row.public_body),
    creditorName: text(row.creditor_name),
    noteType: text(row.note_type),
    amountText: text(row.amount_text),
    citedExcerpt: text(row.cited_excerpt),
    ruleVersion: text(row.rule_version),
    gridArtifactSha256: text(row.grid_artifact_sha256),
    gridRetrievedAt: text(row.grid_retrieved_at),
    sourcePageUrl: text(row.source_page_url),
    reviewMode: text(row.review_mode),
  };
  if (
    Object.values(link).some((value) => value === null) ||
    // Só empenho orçamentário, ligado pela regra ou por revisão humana.
    !COMMITMENT_KEY.test(link.commitmentKey) ||
    !REVIEW_MODES.has(link.reviewMode) ||
    !DATE_TEXT.test(link.issueDateText) ||
    !RULE.test(link.ruleVersion) ||
    !SHA256.test(link.gridArtifactSha256) ||
    !Number.isFinite(Date.parse(link.gridRetrievedAt)) ||
    !link.sourcePageUrl.startsWith("https://") ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return link;
}

export function parseCommitmentLinkRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseLinkRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function groupLinksByContract(links) {
  const grouped = new Map();
  for (const link of links) {
    const current = grouped.get(link.contractPortalId) ?? [];
    current.push(link);
    grouped.set(link.contractPortalId, current);
  }
  return grouped;
}
