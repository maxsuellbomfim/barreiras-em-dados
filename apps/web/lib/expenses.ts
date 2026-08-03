export type PublicExpenseReport = Readonly<{
  expenseReportId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  totalUpdatedAmount: string;
  totalCommittedPeriodAmount: string;
  totalCommittedToDateAmount: string;
  totalLiquidatedPeriodAmount: string;
  totalLiquidatedToDateAmount: string;
  totalPaidPeriodAmount: string;
  totalPaidToDateAmount: string;
  totalUnpaidCommittedAmount: string;
  totalBalanceAmount: string;
  currency: "BRL";
  publicBodyName: string;
  sourceUrl: string;
  documentSourceUrl: string;
  artifactSha256: string;
  documentArtifactSha256: string;
  collectedAt: string;
  methodologyVersion: "public-expense-reports/1.0.0";
  validationStatus: "validated";
}>;

export type ExpenseReportsResult =
  | Readonly<{ state: "available"; reports: readonly PublicExpenseReport[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseExpenseReport(
  row: Record<string, unknown>,
): PublicExpenseReport | null {
  const expenseReportId = optionalString(row.expense_report_id);
  const publicBodyName = optionalString(row.public_body_name);
  const sourceUrl = optionalString(row.source_url);
  const documentSourceUrl = optionalString(row.document_source_url);
  const artifactSha256 = optionalString(row.artifact_sha256);
  const documentArtifactSha256 = optionalString(row.document_artifact_sha256);
  const collectedAt = optionalString(row.collected_at);
  const periodStart = optionalString(row.period_start);
  const periodEnd = optionalString(row.period_end);
  const amountFields = [
    "total_updated_amount",
    "total_committed_period_amount",
    "total_committed_to_date_amount",
    "total_liquidated_period_amount",
    "total_liquidated_to_date_amount",
    "total_paid_period_amount",
    "total_paid_to_date_amount",
    "total_unpaid_committed_amount",
    "total_balance_amount",
  ] as const;
  const amounts = Object.fromEntries(
    amountFields.map((field) => [field, optionalString(row[field])]),
  ) as Record<(typeof amountFields)[number], string | null>;

  if (
    expenseReportId === null ||
    publicBodyName === null ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    documentSourceUrl === null ||
    !documentSourceUrl.startsWith("https://") ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    documentArtifactSha256 === null ||
    !SHA256.test(documentArtifactSha256) ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    periodStart === null ||
    !ISO_DATE.test(periodStart) ||
    periodEnd === null ||
    !ISO_DATE.test(periodEnd) ||
    row.currency !== "BRL" ||
    !Number.isSafeInteger(row.fiscal_year) ||
    row.methodology_version !== "public-expense-reports/1.0.0" ||
    row.validation_status !== "validated" ||
    amountFields.some(
      (field) => amounts[field] === null || !DECIMAL.test(amounts[field] ?? ""),
    )
  ) {
    return null;
  }

  return {
    expenseReportId,
    fiscalYear: Number(row.fiscal_year),
    periodStart,
    periodEnd,
    totalUpdatedAmount: amounts.total_updated_amount as string,
    totalCommittedPeriodAmount: amounts.total_committed_period_amount as string,
    totalCommittedToDateAmount: amounts.total_committed_to_date_amount as string,
    totalLiquidatedPeriodAmount: amounts.total_liquidated_period_amount as string,
    totalLiquidatedToDateAmount: amounts.total_liquidated_to_date_amount as string,
    totalPaidPeriodAmount: amounts.total_paid_period_amount as string,
    totalPaidToDateAmount: amounts.total_paid_to_date_amount as string,
    totalUnpaidCommittedAmount: amounts.total_unpaid_committed_amount as string,
    totalBalanceAmount: amounts.total_balance_amount as string,
    currency: "BRL",
    publicBodyName,
    sourceUrl,
    documentSourceUrl,
    artifactSha256,
    documentArtifactSha256,
    collectedAt,
    methodologyVersion: "public-expense-reports/1.0.0",
    validationStatus: "validated",
  };
}

export async function getPublicExpenseReports(
  fiscalYear?: number,
): Promise<ExpenseReportsResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_expense_reports`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          page_size: 100,
          fiscal_year_filter: fiscalYear ?? null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const reports: PublicExpenseReport[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) {
        return { state: "unavailable" };
      }
      const report = parseExpenseReport(row as Record<string, unknown>);
      if (report === null) return { state: "unavailable" };
      reports.push(report);
    }
    return { state: "available", reports };
  } catch {
    return { state: "unavailable" };
  }
}
