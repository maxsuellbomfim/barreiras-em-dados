const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const METHODOLOGY = "public-expense-source-conflicts/1.0.0";

const FIELD_LABELS = new Map([
  ["total_fixed_amount", "dotação fixada"],
  ["total_additions_amount", "suplementações"],
  ["total_reductions_amount", "anulações"],
  ["total_updated_amount", "dotação atualizada"],
  ["total_committed_period_amount", "despesa empenhada no mês"],
  ["total_committed_to_date_amount", "despesa empenhada acumulada"],
  ["total_liquidated_period_amount", "despesa liquidada no mês"],
  ["total_liquidated_to_date_amount", "despesa liquidada acumulada"],
  ["total_paid_period_amount", "pagamentos no mês"],
  ["total_paid_to_date_amount", "pagamentos acumulados"],
  ["total_unpaid_committed_amount", "despesa empenhada a pagar"],
  ["total_balance_amount", "saldo da dotação"],
]);

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function decimal(value) {
  const serialized = typeof value === "number" && Number.isFinite(value)
    ? String(value)
    : text(value);
  return serialized && DECIMAL.test(serialized) ? serialized : null;
}

export function parseExpenseReportSourceConflicts(payload) {
  if (!Array.isArray(payload)) return { state: "unavailable" };
  const conflicts = [];
  for (const value of payload) {
    if (typeof value !== "object" || value === null) {
      return { state: "unavailable" };
    }
    const reportId = text(value.expense_report_id);
    const periodStart = text(value.period_start);
    const periodEnd = text(value.period_end);
    const fieldName = text(value.field_name);
    const fieldLabel = fieldName ? FIELD_LABELS.get(fieldName) : null;
    const declaredAmount = decimal(value.declared_amount);
    const calculatedAmount = decimal(value.calculated_amount);
    const differenceAmount = decimal(value.difference_amount);
    const documentSourceUrl = text(value.document_source_url);
    const documentArtifactSha256 = text(value.document_artifact_sha256);
    if (
      !reportId || !UUID.test(reportId) ||
      !Number.isSafeInteger(value.fiscal_year) ||
      !periodStart || !ISO_DATE.test(periodStart) ||
      !periodEnd || !ISO_DATE.test(periodEnd) ||
      !fieldName || !fieldLabel ||
      declaredAmount === null || calculatedAmount === null ||
      differenceAmount === null ||
      !documentSourceUrl?.startsWith("https://") ||
      !documentArtifactSha256 || !SHA256.test(documentArtifactSha256) ||
      value.methodology_version !== METHODOLOGY
    ) {
      return { state: "unavailable" };
    }
    conflicts.push({
      expenseReportId: reportId,
      fiscalYear: value.fiscal_year,
      periodStart,
      periodEnd,
      fieldName,
      fieldLabel,
      declaredAmount,
      calculatedAmount,
      differenceAmount,
      documentSourceUrl,
      documentArtifactSha256,
      methodologyVersion: METHODOLOGY,
    });
  }
  return { state: "available", conflicts };
}

export async function getPublicExpenseReportSourceConflicts(fiscalYear) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !Number.isSafeInteger(fiscalYear) || fiscalYear < 1900 || fiscalYear > 2200 ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_expense_report_source_conflicts`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 100, fiscal_year_filter: fiscalYear }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    return parseExpenseReportSourceConflicts(await response.json());
  } catch {
    return { state: "unavailable" };
  }
}
