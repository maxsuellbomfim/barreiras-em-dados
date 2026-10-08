// Citações de contrato em empenhos sem correspondência exata na lista do portal
// (contract-citation-comparison/1.0.0, ADR 0096). Valores chegam como decimal
// em texto e continuam texto: nenhuma conta aqui.
const METHODOLOGIES = new Set(["contract-citation-comparison/1.0.0"]);
const DECIMAL = /^-?\d+\.\d{2}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const KEY = /^O-\d+$/;
const CATEGORIES = new Set(["sem_correspondencia", "publicado_no_pncp"]);
// "automated" = conferência automática por agente, não revisão humana (ADR 0091).
const REVIEW_KINDS = new Set(["human", "automated"]);

export const FIRST_CITATION_YEAR = 2024;

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function isoDate(value) {
  return typeof value === "string" && ISO_DATE.test(value) ? value : null;
}

/**
 * Antes da conferência registrada a função devolve só o estado. Linhas
 * inválidas derrubam o conjunto: comparação pela metade não é publicada.
 */
export function parseContractCitationRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  if (rows.length === 1 && rows[0]?.review_state === "awaiting_review") {
    return METHODOLOGIES.has(rows[0].methodology_version) ? { state: "awaiting_review" } : null;
  }
  const groups = [];
  let approvedAt = null;
  let reviewKind = null;
  for (const row of rows) {
    if (!row || typeof row !== "object" || row.review_state !== "approved") return null;
    const person = row.row_kind === "pf_aggregate";
    const group = {
      kind: person ? "pf_aggregate" : "entity",
      category: CATEGORIES.has(row.category) ? row.category : null,
      publicBody: text(row.public_body),
      // Pessoa física: sem nome, número, trecho ou chave do empenho.
      creditorName: person ? null : text(row.creditor_name),
      citedNumber: person ? null : text(row.cited_number),
      citedExcerpt: person ? null : text(row.cited_excerpt),
      commitments: count(row.commitments),
      payments: count(row.payments),
      unreadablePayments: count(row.unreadable_payments),
      paidAmount: typeof row.paid_amount === "string" && DECIMAL.test(row.paid_amount)
        ? row.paid_amount : null,
      firstIssueDate: isoDate(row.first_issue_date),
      lastIssueDate: isoDate(row.last_issue_date),
      listReadOn: isoDate(row.list_read_on),
      latestCommitmentKey: person ? null : text(row.latest_commitment_key),
      pncpUrl: person ? null : text(row.pncp_url),
      sourcePageUrl: text(row.source_page_url),
    };
    if (
      (!person && row.row_kind !== "entity") ||
      group.category === null ||
      group.publicBody === null ||
      (!person && (group.creditorName === null || group.citedNumber === null ||
        !KEY.test(group.latestCommitmentKey ?? ""))) ||
      (person && (row.creditor_name !== null || row.latest_commitment_key !== null)) ||
      !group.commitments ||
      group.payments === null ||
      group.unreadablePayments === null ||
      group.paidAmount === null ||
      group.firstIssueDate === null ||
      group.lastIssueDate === null ||
      group.listReadOn === null ||
      (group.category === "publicado_no_pncp" && !person &&
        !group.pncpUrl?.startsWith("https://pncp.gov.br/")) ||
      !group.sourcePageUrl?.startsWith("https://") ||
      typeof row.approved_at !== "string" ||
      !REVIEW_KINDS.has(row.review_kind) ||
      !METHODOLOGIES.has(row.methodology_version)
    ) {
      return null;
    }
    approvedAt ??= row.approved_at;
    reviewKind ??= row.review_kind;
    groups.push(group);
  }
  return { state: "approved", approvedAt, reviewKind, groups };
}

export function citationYear(value, currentYear) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isSafeInteger(parsed) && parsed >= FIRST_CITATION_YEAR && parsed <= currentYear
    ? parsed
    : currentYear;
}

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

export async function getPublicContractCitations(year) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_contract_citations`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ p_year: year }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return { state: "unavailable" };
    return parseContractCitationRows(await response.json()) ?? { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
