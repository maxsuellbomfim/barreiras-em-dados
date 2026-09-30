// Dívida consolidada declarada no RGF-Anexo 02 (municipal-debt-rgf-annex2/1.0.0).
// Valores chegam e ficam como decimal em texto: nenhuma conta aqui.
const METHODOLOGY = "municipal-debt-rgf-annex2/1.0.0";
const DECIMAL = /^-?\d+(?:\.\d+)?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalDecimal(value) {
  if (value === null) return { ok: true, value: null };
  return typeof value === "string" && DECIMAL.test(value)
    ? { ok: true, value }
    : { ok: false };
}

function parseComposition(value) {
  if (!Array.isArray(value)) return null;
  const lines = [];
  for (const line of value) {
    const code = text(line?.code);
    const account = text(line?.account);
    if (code === null || account === null || typeof line.value !== "string") return null;
    if (!DECIMAL.test(line.value)) return null;
    lines.push({ code, account, value: line.value });
  }
  return lines;
}

/** Qualquer linha fora do contrato derruba o conjunto. */
export function parseDebtStatementRows(rows) {
  if (!Array.isArray(rows)) return null;
  const statements = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const decimals = {};
    for (const [key, source] of [
      ["consolidatedDebt", "consolidated_debt"],
      ["deductions", "deductions"],
      ["netConsolidatedDebt", "net_consolidated_debt"],
      ["adjustedNetCurrentRevenue", "adjusted_net_current_revenue"],
      ["netDebtRevenuePercent", "net_debt_revenue_percent"],
      ["senateLimit", "senate_limit"],
      ["alertLimit", "alert_limit"],
    ]) {
      const parsed = optionalDecimal(row[source]);
      if (!parsed.ok) return null;
      decimals[key] = parsed.value;
    }
    const composition = parseComposition(row.composition);
    const sourceUrl = text(row.source_url);
    if (
      !Number.isSafeInteger(row.fiscal_year) ||
      row.fiscal_year < 2015 ||
      ![1, 2, 3].includes(row.period) ||
      typeof row.period_end !== "string" ||
      !ISO_DATE.test(row.period_end) ||
      composition === null ||
      typeof row.artifact_sha256 !== "string" ||
      !SHA256.test(row.artifact_sha256) ||
      text(row.retrieved_at) === null ||
      sourceUrl === null ||
      !sourceUrl.startsWith("https://") ||
      row.methodology_version !== METHODOLOGY
    ) {
      return null;
    }
    statements.push({
      fiscalYear: row.fiscal_year,
      period: row.period,
      periodEnd: row.period_end,
      ...decimals,
      composition,
      artifactSha256: row.artifact_sha256,
      retrievedAt: text(row.retrieved_at),
      sourceUrl,
    });
  }
  // O mais recente primeiro, sem depender da ordem da resposta.
  return statements.sort(
    (left, right) => right.fiscalYear - left.fiscalYear || right.period - left.period,
  );
}

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

export async function getPublicDebtStatements() {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_debt_statements`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: "{}",
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const statements = parseDebtStatementRows(await response.json());
    return statements ? { state: "available", statements } : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
