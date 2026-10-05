// Retenções da folha publicadas como empenhos extraorçamentários
// (municipal-payroll-withholdings/1.0.0). Valores chegam como decimal em
// texto e continuam texto: nenhuma conta aqui.
const METHODOLOGIES = new Set(["municipal-payroll-withholdings/1.0.0"]);
const DECIMAL = /^-?\d+\.\d{2}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const MONTH = /^\d{4}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const KEY = /^E-\d+$/;

export const FIRST_WITHHOLDING_YEAR = 2024;

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function decimal(value) {
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function parseMonths(value) {
  if (!Array.isArray(value)) return null;
  const months = value.map((item) => ({
    month: typeof item?.month === "string" && MONTH.test(item.month) ? item.month : null,
    commitments: count(item?.commitments),
    amount: decimal(item?.amount),
  }));
  return months.every((item) => item.month && item.commitments && item.amount !== null)
    ? months
    : null;
}

/** Linhas inválidas derrubam o conjunto: número pela metade não é publicado. */
export function parsePayrollWithholdingRows(rows) {
  if (!Array.isArray(rows)) return null;
  const creditors = [];
  let summary = null;
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const creditor = {
      // null = pessoas físicas e pensão alimentícia, somadas sem nome.
      creditorName: row.creditor_name === null ? null : text(row.creditor_name),
      commitments: count(row.commitments),
      amount: decimal(row.amount),
      reversalAmount: decimal(row.reversal_amount),
      firstCommitmentDate: typeof row.first_commitment_date === "string" &&
        ISO_DATE.test(row.first_commitment_date) ? row.first_commitment_date : null,
      lastCommitmentDate: typeof row.last_commitment_date === "string" &&
        ISO_DATE.test(row.last_commitment_date) ? row.last_commitment_date : null,
      latestCommitmentKey: text(row.latest_commitment_key),
      gridArtifactSha256: text(row.grid_artifact_sha256),
    };
    const rowSummary = {
      commitments: count(row.year_commitments),
      amount: decimal(row.year_amount),
      reversalAmount: decimal(row.year_reversal_amount),
      gridMonths: count(row.year_grid_months),
      linkedPayments: count(row.year_linked_payments),
      months: parseMonths(row.year_months),
      sourcePageUrl: text(row.source_page_url),
    };
    if (
      (row.creditor_name !== null && creditor.creditorName === null) ||
      !creditor.commitments ||
      creditor.amount === null ||
      creditor.reversalAmount === null ||
      creditor.firstCommitmentDate === null ||
      creditor.lastCommitmentDate === null ||
      !KEY.test(creditor.latestCommitmentKey ?? "") ||
      !SHA256.test(creditor.gridArtifactSha256 ?? "") ||
      Object.values(rowSummary).some((value) => value === null) ||
      !rowSummary.sourcePageUrl.startsWith("https://") ||
      !METHODOLOGIES.has(row.methodology_version)
    ) {
      return null;
    }
    summary ??= rowSummary;
    creditors.push(creditor);
  }
  return { summary, creditors };
}

export function withholdingYear(value, currentYear) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isSafeInteger(parsed) && parsed >= FIRST_WITHHOLDING_YEAR && parsed <= currentYear
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

export async function getPublicPayrollWithholdings(year) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_payroll_withholdings`, {
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
    const parsed = parsePayrollWithholdingRows(await response.json());
    return parsed ? { state: "available", ...parsed } : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
