export type PublicFinanceCoverageRow = Readonly<{
  coverageId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  publicBodyName: string;
  revenueReportCount: number;
  expenseReportCount: number;
  coverageStatus: "complete" | "needs_review" | "revenue_only" | "expense_only" | "missing";
  coverageNote: string;
  calculationMethodology: "finance-coverage/1.0.0";
}>;

export type PublicFinanceCoverageResult =
  | Readonly<{ state: "available"; rows: readonly PublicFinanceCoverageRow[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function repairMojibake(value: string): string {
  if (!/[ÃƒÃ‚]/.test(value)) return value;
  try {
    const bytes = Uint8Array.from(Array.from(value), (character) => character.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return value;
  }
}

function integer(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function parseRow(row: Record<string, unknown>): PublicFinanceCoverageRow | null {
  const coverageId = text(row.coverage_id);
  const periodStart = text(row.period_start);
  const periodEnd = text(row.period_end);
  const publicBodyName = text(row.public_body_name);
  const coverageNoteValue = text(row.coverage_note);
  const coverageNote = coverageNoteValue ? repairMojibake(coverageNoteValue) : null;
  const fiscalYear = row.fiscal_year;
  const revenueReportCount = integer(row.revenue_report_count);
  const expenseReportCount = integer(row.expense_report_count);
  const coverageStatus = row.coverage_status;
  if (
    !coverageId || !periodStart || !ISO_DATE.test(periodStart) || !periodEnd ||
    !ISO_DATE.test(periodEnd) || !publicBodyName || !coverageNote ||
    !Number.isSafeInteger(fiscalYear) || revenueReportCount === null ||
    expenseReportCount === null ||
    !["complete", "needs_review", "revenue_only", "expense_only", "missing"].includes(String(coverageStatus)) ||
    row.calculation_methodology !== "finance-coverage/1.0.0"
  ) return null;
  return {
    coverageId,
    fiscalYear: Number(fiscalYear),
    periodStart,
    periodEnd,
    publicBodyName,
    revenueReportCount,
    expenseReportCount,
    coverageStatus: coverageStatus as PublicFinanceCoverageRow["coverageStatus"],
    coverageNote,
    calculationMethodology: "finance-coverage/1.0.0",
  };
}

export async function getPublicFinanceCoverage(): Promise<PublicFinanceCoverageResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_finance_coverage`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ page_size: 120, fiscal_year_from: 2021, fiscal_year_to: null }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows: PublicFinanceCoverageRow[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) continue;
      const parsed = parseRow(row as Record<string, unknown>);
      if (parsed) rows.push(parsed);
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}
