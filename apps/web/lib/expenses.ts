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

export type PublicExpenseLine = Readonly<{
  expenseLineId: string;
  expenseReportId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  lineNumber: number;
  expenseCode: string;
  description: string;
  sourceCode: string;
  fixedAmount: string;
  additionsAmount: string;
  reductionsAmount: string;
  updatedAmount: string;
  committedPeriodAmount: string;
  committedToDateAmount: string;
  liquidatedPeriodAmount: string;
  liquidatedToDateAmount: string;
  paidPeriodAmount: string;
  paidToDateAmount: string;
  unpaidCommittedAmount: string;
  balanceAmount: string;
  currency: "BRL";
  sourceUrl: string;
  documentSourceUrl: string;
  documentArtifactSha256: string;
  methodologyVersion: "public-expense-lines/1.0.0";
}>;

export type ExpenseLinesResult =
  | Readonly<{ state: "available"; lines: readonly PublicExpenseLine[] }>
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

function parseExpenseLine(
  row: Record<string, unknown>,
): PublicExpenseLine | null {
  const stringFields = {
    expenseLineId: optionalString(row.expense_line_id),
    expenseReportId: optionalString(row.expense_report_id),
    expenseCode: optionalString(row.expense_code),
    description: optionalString(row.description),
    sourceCode: optionalString(row.source_code),
    periodStart: optionalString(row.period_start),
    periodEnd: optionalString(row.period_end),
    sourceUrl: optionalString(row.source_url),
    documentSourceUrl: optionalString(row.document_source_url),
    documentArtifactSha256: optionalString(row.document_artifact_sha256),
  };
  const amountFields = [
    "fixed_amount",
    "additions_amount",
    "reductions_amount",
    "updated_amount",
    "committed_period_amount",
    "committed_to_date_amount",
    "liquidated_period_amount",
    "liquidated_to_date_amount",
    "paid_period_amount",
    "paid_to_date_amount",
    "unpaid_committed_amount",
    "balance_amount",
  ] as const;
  const amounts = Object.fromEntries(
    amountFields.map((field) => [field, optionalString(row[field])]),
  ) as Record<(typeof amountFields)[number], string | null>;

  if (
    Object.values(stringFields).some((value) => value === null) ||
    !stringFields.sourceUrl?.startsWith("https://") ||
    !stringFields.documentSourceUrl?.startsWith("https://") ||
    !stringFields.documentArtifactSha256 ||
    !SHA256.test(stringFields.documentArtifactSha256) ||
    !ISO_DATE.test(stringFields.periodStart ?? "") ||
    !ISO_DATE.test(stringFields.periodEnd ?? "") ||
    row.currency !== "BRL" ||
    !Number.isSafeInteger(row.fiscal_year) ||
    !Number.isSafeInteger(row.line_number) ||
    row.methodology_version !== "public-expense-lines/1.0.0" ||
    amountFields.some(
      (field) => amounts[field] === null || !DECIMAL.test(amounts[field] ?? ""),
    )
  ) {
    return null;
  }

  return {
    expenseLineId: stringFields.expenseLineId as string,
    expenseReportId: stringFields.expenseReportId as string,
    fiscalYear: Number(row.fiscal_year),
    periodStart: stringFields.periodStart as string,
    periodEnd: stringFields.periodEnd as string,
    lineNumber: Number(row.line_number),
    expenseCode: stringFields.expenseCode as string,
    description: stringFields.description as string,
    sourceCode: stringFields.sourceCode as string,
    fixedAmount: amounts.fixed_amount as string,
    additionsAmount: amounts.additions_amount as string,
    reductionsAmount: amounts.reductions_amount as string,
    updatedAmount: amounts.updated_amount as string,
    committedPeriodAmount: amounts.committed_period_amount as string,
    committedToDateAmount: amounts.committed_to_date_amount as string,
    liquidatedPeriodAmount: amounts.liquidated_period_amount as string,
    liquidatedToDateAmount: amounts.liquidated_to_date_amount as string,
    paidPeriodAmount: amounts.paid_period_amount as string,
    paidToDateAmount: amounts.paid_to_date_amount as string,
    unpaidCommittedAmount: amounts.unpaid_committed_amount as string,
    balanceAmount: amounts.balance_amount as string,
    currency: "BRL",
    sourceUrl: stringFields.sourceUrl as string,
    documentSourceUrl: stringFields.documentSourceUrl as string,
    documentArtifactSha256: stringFields.documentArtifactSha256 as string,
    methodologyVersion: "public-expense-lines/1.0.0",
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

export async function getPublicExpenseLines(
  reportId?: string,
  pageSize = 25,
): Promise<ExpenseLinesResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_public_expense_lines`,
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
          report_filter: reportId ?? null,
          page_size: pageSize,
          page_offset: 0,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const lines: PublicExpenseLine[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) {
        return { state: "unavailable" };
      }
      const line = parseExpenseLine(row as Record<string, unknown>);
      if (line === null) return { state: "unavailable" };
      lines.push(line);
    }
    return { state: "available", lines };
  } catch {
    return { state: "unavailable" };
  }
}
