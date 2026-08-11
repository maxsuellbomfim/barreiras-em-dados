const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^\d+(?:\.\d{1,2})?$/;
const ALLOWED_TYPES = new Set([
  "loan",
  "precatorio",
  "accounts_payable",
  "restos_a_pagar_total",
  "restos_a_pagar_processados",
  "restos_a_pagar_nao_processados",
  "social_security",
  "court_order",
  "other",
]);
const ALLOWED_STATUSES = new Set([
  "reported",
  "active",
  "settled",
  "suspended",
  "disputed",
  "unknown",
]);
const ALLOWED_VALIDATION_STATES = new Set(["validated", "reconciled"]);

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value.trim())) return value.trim();
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Number.isSafeInteger(value * 100) &&
    value >= 0
  ) {
    const normalized = String(value);
    return DECIMAL.test(normalized) ? normalized : null;
  }
  return null;
}

function optionalDecimal(value) {
  return value === null ? null : decimal(value);
}

function cents(value) {
  const [integer, fraction = ""] = value.split(".");
  return BigInt(integer) * 100n + BigInt(fraction.padEnd(2, "0"));
}

function parseRow(row) {
  const obligationId = text(row.obligation_id);
  const obligationType = text(row.obligation_type);
  const description = text(row.description);
  const periodStart = row.period_start === null ? null : text(row.period_start);
  const periodEnd = text(row.period_end);
  const paymentsPriorAmount = optionalDecimal(row.payments_prior_amount);
  const paymentsPeriodAmount = optionalDecimal(row.payments_amount);
  const paymentsToDateAmount = optionalDecimal(row.payments_to_date_amount);
  const sourceUrl = text(row.source_url);
  const artifactSha256 = text(row.artifact_sha256);
  const sourceRetrievedAt = text(row.source_retrieved_at);
  const documentSourceUrl = text(row.document_source_url);
  const documentArtifactSha256 = text(row.document_artifact_sha256);
  const documentRetrievedAt = text(row.document_retrieved_at);
  const methodologyVersion = text(row.methodology_version);
  if (
    obligationId === null ||
    obligationType === null ||
    !ALLOWED_TYPES.has(obligationType) ||
    description === null ||
    !Number.isSafeInteger(row.fiscal_year) ||
    (periodStart !== null && !ISO_DATE.test(periodStart)) ||
    periodEnd === null ||
    !ISO_DATE.test(periodEnd) ||
    !ALLOWED_STATUSES.has(row.status) ||
    !ALLOWED_VALIDATION_STATES.has(row.validation_state) ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    sourceRetrievedAt === null ||
    Number.isNaN(Date.parse(sourceRetrievedAt)) ||
    documentSourceUrl === null ||
    !documentSourceUrl.startsWith("https://") ||
    documentArtifactSha256 === null ||
    !SHA256.test(documentArtifactSha256) ||
    documentRetrievedAt === null ||
    Number.isNaN(Date.parse(documentRetrievedAt)) ||
    methodologyVersion === null
  ) {
    return null;
  }
  if (
    obligationType === "restos_a_pagar_total" &&
    (paymentsPriorAmount === null ||
      paymentsPeriodAmount === null ||
      paymentsToDateAmount === null ||
      cents(paymentsPriorAmount) + cents(paymentsPeriodAmount) !==
        cents(paymentsToDateAmount))
  ) {
    return null;
  }

  return {
    obligationId,
    obligationType,
    description,
    fiscalYear: row.fiscal_year,
    periodStart,
    periodEnd,
    openingBalance: optionalDecimal(row.opening_balance),
    additionsAmount: optionalDecimal(row.additions_amount),
    reductionsAmount: optionalDecimal(row.reductions_amount),
    paymentsPriorAmount,
    paymentsPeriodAmount,
    paymentsToDateAmount,
    closingBalance: optionalDecimal(row.closing_balance),
    status: row.status,
    validationState: row.validation_state,
    sourceUrl,
    artifactSha256,
    sourceRetrievedAt,
    documentSourceUrl,
    documentArtifactSha256,
    documentRetrievedAt,
    methodologyVersion,
  };
}

export async function getPublicObligations(fiscalYear, obligationType) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_obligations`,
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
          obligation_type_filter: obligationType ?? null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const obligations = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) return { state: "unavailable" };
      const obligation = parseRow(row);
      if (obligation === null) return { state: "unavailable" };
      obligations.push(obligation);
    }
    return { state: "available", obligations };
  } catch {
    return { state: "unavailable" };
  }
}
