import { isMonthlyFinanceCommentaryCompatible } from "./monthly-finance-commentary.mjs";

export type PublicMonthlyFinanceClosure = Readonly<{
  closureId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  publicBodyName: string;
  revenueReportAmount: string | null;
  revenueReportCount: number;
  revenueLineCount: number;
  expensePaidAmount: string | null;
  expenseCommittedAmount: string | null;
  expenseLiquidatedAmount: string | null;
  expenseReportCount: number;
  operationalDifferenceAmount: string | null;
  closureStatus: "operational" | "needs_data" | "needs_review";
  coverageNote: string;
  calculationMethodology: "monthly-finance-closure/1.1.0";
  aiCommentary: string | null;
}>;

type PublicMonthlyFinanceCommentary = Readonly<{
  closureId: string;
  commentary: string;
  statementClass: "fact" | "methodology";
}>;

export type MonthlyFinanceResult =
  | Readonly<{
      state: "available";
      closures: readonly PublicMonthlyFinanceClosure[];
    }>
  | Readonly<{ state: "unavailable" }>;

export type MonthlyFinanceDetailResult =
  | Readonly<{
      state: "available";
      detail: PublicMonthlyFinanceDetail;
    }>
  | Readonly<{ state: "not_found" }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function repairMojibake(value: string): string {
  if (!/[ÃÂ]/.test(value)) return value;
  try {
    const bytes = Uint8Array.from(Array.from(value), (character) => character.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return value;
  }
}

function decimal(value: unknown): string | null {
  if (typeof value === "string" && DECIMAL.test(value.trim())) return value.trim();
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Math.abs(value) <= Number.MAX_SAFE_INTEGER
  ) {
    const normalized = String(value);
    return DECIMAL.test(normalized) ? normalized : null;
  }
  return null;
}

function integer(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function parseClosure(row: Record<string, unknown>): PublicMonthlyFinanceClosure | null {
  const closureId = text(row.closure_id);
  const periodStart = text(row.period_start);
  const periodEnd = text(row.period_end);
  const publicBodyName = text(row.public_body_name);
  const coverageNoteValue = text(row.coverage_note);
  const coverageNote = coverageNoteValue ? repairMojibake(coverageNoteValue) : null;
  const methodology = row.calculation_methodology;
  const status = row.closure_status;
  const fiscalYear = row.fiscal_year;
  const revenueReportCount = integer(row.revenue_report_count);
  const revenueLineCount = integer(row.revenue_line_count);
  const expenseReportCount = integer(row.expense_report_count);
  if (
    !closureId ||
    !periodStart ||
    !ISO_DATE.test(periodStart) ||
    !periodEnd ||
    !ISO_DATE.test(periodEnd) ||
    !publicBodyName ||
    !coverageNote ||
    methodology !== "monthly-finance-closure/1.1.0" ||
    (status !== "operational" && status !== "needs_data" && status !== "needs_review") ||
    !Number.isSafeInteger(fiscalYear) ||
    revenueReportCount === null ||
    revenueLineCount === null ||
    expenseReportCount === null
  ) {
    return null;
  }
  const revenueReportAmount = decimal(row.revenue_report_amount);
  const expensePaidAmount = decimal(row.expense_paid_amount);
  const expenseCommittedAmount = decimal(row.expense_committed_amount);
  const expenseLiquidatedAmount = decimal(row.expense_liquidated_amount);
  const operationalDifferenceAmount = decimal(row.operational_difference_amount);
  if (
    (row.revenue_report_amount !== null && revenueReportAmount === null) ||
    (row.expense_paid_amount !== null && expensePaidAmount === null) ||
    (row.expense_committed_amount !== null && expenseCommittedAmount === null) ||
    (row.expense_liquidated_amount !== null && expenseLiquidatedAmount === null) ||
    (row.operational_difference_amount !== null && operationalDifferenceAmount === null)
  ) {
    return null;
  }
  return {
    closureId,
    fiscalYear: Number(fiscalYear),
    periodStart,
    periodEnd,
    publicBodyName,
    revenueReportAmount,
    revenueReportCount,
    revenueLineCount,
    expensePaidAmount,
    expenseCommittedAmount,
    expenseLiquidatedAmount,
    expenseReportCount,
    operationalDifferenceAmount,
    closureStatus: status,
    coverageNote,
    calculationMethodology: "monthly-finance-closure/1.1.0",
    aiCommentary: null,
  };
}

function parseCommentary(
  row: Record<string, unknown>,
): PublicMonthlyFinanceCommentary | null {
  const closureId = text(row.closure_id);
  const commentary = text(row.commentary);
  const statementClass = row.statement_class;
  if (
    !closureId ||
    !commentary ||
    commentary.length > 900 ||
    /\d/.test(commentary) ||
    (statementClass !== "fact" && statementClass !== "methodology")
  ) {
    return null;
  }
  return {
    closureId,
    commentary,
    statementClass,
  };
}

export async function getPublicMonthlyFinanceClosures(
  fiscalYear?: number,
): Promise<MonthlyFinanceResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const request = {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        page_size: 24,
        fiscal_year_filter: fiscalYear ?? null,
      }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    } satisfies RequestInit;
    const [response, commentaryResponse] = await Promise.all([
      fetch(`${supabaseUrl}/rest/v1/rpc/get_public_monthly_finance_closures`, request),
      fetch(`${supabaseUrl}/rest/v1/rpc/get_public_monthly_finance_commentaries`, request),
    ]);
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const closures: PublicMonthlyFinanceClosure[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) return { state: "unavailable" };
      const closure = parseClosure(row as Record<string, unknown>);
      if (!closure) return { state: "unavailable" };
      closures.push(closure);
    }
    const commentaryByClosure = new Map<string, PublicMonthlyFinanceCommentary>();
    if (commentaryResponse.ok) {
      const commentaryPayload = await commentaryResponse.json();
      if (Array.isArray(commentaryPayload)) {
        for (const row of commentaryPayload) {
          if (typeof row !== "object" || row === null) continue;
          const commentary = parseCommentary(row as Record<string, unknown>);
          if (commentary) commentaryByClosure.set(commentary.closureId, commentary);
        }
      }
    }
    return {
      state: "available",
      closures: closures.map((closure) => {
        const commentary = commentaryByClosure.get(closure.closureId);
        return {
          ...closure,
          aiCommentary:
            commentary &&
            isMonthlyFinanceCommentaryCompatible(
              closure.closureStatus,
              commentary.commentary,
            )
              ? commentary.commentary
              : null,
        };
      }),
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicMonthlyFinanceDetail(
  periodStart: string,
): Promise<MonthlyFinanceDetailResult> {
  if (periodStartFromSlug(periodStart.slice(0, 7)) !== periodStart) {
    return { state: "not_found" };
  }
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_monthly_finance_detail`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ period_filter: periodStart }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    if (payload.length === 0) return { state: "not_found" };
    if (payload.length !== 1 || typeof payload[0] !== "object" || payload[0] === null) {
      return { state: "unavailable" };
    }
    const detail = parseMonthlyFinanceDetail(payload[0] as Record<string, unknown>);
    if (!detail || detail.periodStart !== periodStart) return { state: "unavailable" };
    return { state: "available", detail };
  } catch {
    return { state: "unavailable" };
  }
}
import {
  parseMonthlyFinanceDetail,
  periodStartFromSlug,
  type PublicMonthlyFinanceDetail,
} from "./monthly-finance-detail.mjs";
