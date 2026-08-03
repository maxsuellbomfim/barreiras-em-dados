export type PublicFinanceSignal = Readonly<{
  findingId: string;
  ruleSlug: string;
  ruleName: string;
  severity: "information" | "low" | "medium" | "high";
  targetType: string;
  targetId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  publicBodyName: string;
  publicExplanation: string;
  deterministicOutput: Record<string, unknown>;
  sourceUrl: string | null;
  artifactSha256: string | null;
  createdAt: string;
}>;

export type PublicFinanceSignalsResult =
  | Readonly<{ state: "available"; signals: readonly PublicFinanceSignal[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseSignal(row: Record<string, unknown>): PublicFinanceSignal | null {
  const findingId = text(row.finding_id);
  const ruleSlug = text(row.rule_slug);
  const ruleName = text(row.rule_name);
  const targetType = text(row.target_type);
  const targetId = text(row.target_id);
  const periodStart = text(row.period_start);
  const periodEnd = text(row.period_end);
  const publicBodyName = text(row.public_body_name);
  const publicExplanation = text(row.public_explanation);
  const createdAt = text(row.created_at);
  const fiscalYear = row.fiscal_year;
  const severity = row.severity;
  const output = row.deterministic_output;
  if (
    !findingId || !ruleSlug || !ruleName || !targetType || !targetId ||
    !periodStart || !ISO_DATE.test(periodStart) || !periodEnd ||
    !ISO_DATE.test(periodEnd) || !publicBodyName || !publicExplanation ||
    !createdAt || !Number.isSafeInteger(fiscalYear) || typeof output !== "object" ||
    output === null || Array.isArray(output) ||
    !["information", "low", "medium", "high"].includes(String(severity))
  ) return null;
  const sourceUrl = text(row.source_url);
  const artifactSha256 = text(row.artifact_sha256);
  return {
    findingId,
    ruleSlug,
    ruleName,
    severity: severity as PublicFinanceSignal["severity"],
    targetType,
    targetId,
    fiscalYear: Number(fiscalYear),
    periodStart,
    periodEnd,
    publicBodyName,
    publicExplanation,
    deterministicOutput: output as Record<string, unknown>,
    sourceUrl: sourceUrl?.startsWith("https://") ? sourceUrl : null,
    artifactSha256: artifactSha256 && SHA256.test(artifactSha256) ? artifactSha256 : null,
    createdAt,
  };
}

export async function getPublicFinanceSignals(): Promise<PublicFinanceSignalsResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_finance_signals`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ page_size: 50 }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const signals: PublicFinanceSignal[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) continue;
      const signal = parseSignal(row as Record<string, unknown>);
      if (signal) signals.push(signal);
    }
    return { state: "available", signals };
  } catch {
    return { state: "unavailable" };
  }
}
