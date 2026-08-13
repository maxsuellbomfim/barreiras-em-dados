export type ParliamentaryAuthorKind =
  | "person"
  | "commission"
  | "bench"
  | "collective"
  | "other";

export type ParliamentaryRepresentativeSourceKind = "federal" | "state";
export type ParliamentaryAuthorAssociationStatus =
  | "approved_official_crosswalk"
  | "not_linked"
  | "not_applicable_collective";

export type ParliamentaryTransferRanking = Readonly<{
  rankPosition: number;
  authorKey: string;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  representativeSourceKind: ParliamentaryRepresentativeSourceKind | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: ParliamentaryAuthorAssociationStatus;
  amendmentCount: number;
  destinationAmount: string;
  committedAmount: string | null;
  paidAmount: string | null;
  fullyPaidAmendmentCount: number;
  firstYear: number;
  lastYear: number;
  methodologyVersion: "parliamentary-transfer-ranking/1.1.0";
}>;

export type ParliamentaryTransferRankingsResult =
  | Readonly<{
      state: "available";
      people: readonly ParliamentaryTransferRanking[];
      collectives: readonly ParliamentaryTransferRanking[];
    }>
  | Readonly<{ state: "unavailable" }>;

export type ParliamentaryTransfer = Readonly<{
  externalTransferKey: string;
  proposalId: string;
  distributionId: string;
  fiscalYear: number;
  amendmentNumber: string | null;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  amendmentKind: string | null;
  beneficiaryName: string | null;
  objectDescription: string | null;
  proposalStatus: string | null;
  proposalAmount: string | null;
  destinationAmount: string;
  committedAmount: string | null;
  paidAmount: string | null;
  bankOrderNumber: string | null;
  bankOrderDate: string | null;
  stageAttributionStatus:
    | "exact_single_distribution"
    | "ambiguous_multiple_distributions";
  collectedAt: string;
  sourceUrl: string;
  artifactSha256: string;
  methodologyVersion: "parliamentary-transfers/1.0.0";
}>;

export type ParliamentaryTransfersResult =
  | Readonly<{
      state: "available";
      people: readonly ParliamentaryTransferRanking[];
      collectives: readonly ParliamentaryTransferRanking[];
      transfers: readonly ParliamentaryTransfer[];
    }>
  | Readonly<{ state: "unavailable" }>;

const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const AUTHOR_KINDS = new Set<ParliamentaryAuthorKind>([
  "person",
  "commission",
  "bench",
  "collective",
  "other",
]);

function requiredText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value: unknown): string | null {
  return value === null || value === undefined ? null : requiredText(value);
}

function decimal(value: unknown): string | null {
  if (typeof value === "string" && DECIMAL.test(value.trim())) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) {
    const roundedCents = Math.round(value * 100);
    if (!Number.isSafeInteger(roundedCents)) return null;
    const normalizedValue = roundedCents / 100;
    const tolerance = Number.EPSILON * Math.max(1, Math.abs(value)) * 4;
    if (Math.abs(value - normalizedValue) > tolerance) return null;
    return normalizedValue.toFixed(2);
  }
  return null;
}

function integer(value: unknown, minimum = 0): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum
    ? value
    : null;
}

function authorKind(value: unknown): ParliamentaryAuthorKind | null {
  return typeof value === "string" && AUTHOR_KINDS.has(value as ParliamentaryAuthorKind)
    ? (value as ParliamentaryAuthorKind)
    : null;
}

function parseRanking(
  row: Record<string, unknown>,
): ParliamentaryTransferRanking | null {
  const rankPosition = integer(row.rank_position, 1);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const representativeSourceKind = optionalText(row.representative_source_kind);
  const representativeExternalId = optionalText(row.representative_external_id);
  const representativeProfileUrl = optionalText(row.representative_profile_url);
  const associationStatus = optionalText(row.association_status);
  const amendmentCount = integer(row.amendment_count);
  const destinationAmount = decimal(row.destination_amount);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const fullyPaidAmendmentCount = integer(row.fully_paid_amendment_count);
  const firstYear = integer(row.first_year, 1900);
  const lastYear = integer(row.last_year, 1900);
  if (
    rankPosition === null || !authorKey || !authorName || !kind ||
    amendmentCount === null || !destinationAmount ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null) ||
    fullyPaidAmendmentCount === null || firstYear === null || lastYear === null ||
    !["approved_official_crosswalk", "not_linked", "not_applicable_collective"].includes(
      associationStatus ?? "",
    ) ||
    (associationStatus === "approved_official_crosswalk" && (
      !["federal", "state"].includes(representativeSourceKind ?? "") ||
      !representativeExternalId || !representativeProfileUrl?.startsWith("https://")
    )) ||
    (associationStatus !== "approved_official_crosswalk" && (
      representativeSourceKind !== null || representativeExternalId !== null ||
      representativeProfileUrl !== null
    )) ||
    row.methodology_version !== "parliamentary-transfer-ranking/1.1.0"
  ) return null;
  return {
    rankPosition,
    authorKey,
    authorName,
    authorKind: kind,
    representativeSourceKind:
      representativeSourceKind as ParliamentaryRepresentativeSourceKind | null,
    representativeExternalId,
    representativeProfileUrl,
    associationStatus: associationStatus as ParliamentaryAuthorAssociationStatus,
    amendmentCount,
    destinationAmount,
    committedAmount,
    paidAmount,
    fullyPaidAmendmentCount,
    firstYear,
    lastYear,
    methodologyVersion: "parliamentary-transfer-ranking/1.1.0",
  };
}

function parseRankingRows(rows: unknown[]): ParliamentaryTransferRanking[] {
  return rows.flatMap((row) => {
    if (typeof row !== "object" || row === null) return [];
    const parsed = parseRanking(row as Record<string, unknown>);
    return parsed ? [parsed] : [];
  });
}

function parseTransfer(row: Record<string, unknown>): ParliamentaryTransfer | null {
  const externalTransferKey = requiredText(row.external_transfer_key);
  const proposalId = requiredText(row.proposal_id);
  const distributionId = requiredText(row.distribution_id);
  const fiscalYear = integer(row.fiscal_year, 1900);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const destinationAmount = decimal(row.destination_amount);
  const proposalAmount = row.proposal_amount === null ? null : decimal(row.proposal_amount);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const collectedAt = requiredText(row.collected_at);
  const sourceUrl = requiredText(row.source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const bankOrderDate = optionalText(row.bank_order_date);
  const stageAttributionStatus = row.stage_attribution_status;
  if (
    !externalTransferKey || !proposalId || !distributionId || fiscalYear === null ||
    !authorName || !kind || !destinationAmount ||
    (row.proposal_amount !== null && proposalAmount === null) ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null) ||
    !collectedAt || Number.isNaN(Date.parse(collectedAt)) ||
    !sourceUrl?.startsWith("https://") || !artifactSha256 || !SHA256.test(artifactSha256) ||
    (bankOrderDate !== null && !ISO_DATE.test(bankOrderDate)) ||
    !["exact_single_distribution", "ambiguous_multiple_distributions"].includes(
      String(stageAttributionStatus),
    ) || row.methodology_version !== "parliamentary-transfers/1.0.0"
  ) return null;
  return {
    externalTransferKey,
    proposalId,
    distributionId,
    fiscalYear,
    amendmentNumber: optionalText(row.amendment_number),
    authorName,
    authorKind: kind,
    amendmentKind: optionalText(row.amendment_kind),
    beneficiaryName: optionalText(row.beneficiary_name),
    objectDescription: optionalText(row.object_description),
    proposalStatus: optionalText(row.proposal_status),
    proposalAmount,
    destinationAmount,
    committedAmount,
    paidAmount,
    bankOrderNumber: optionalText(row.bank_order_number),
    bankOrderDate,
    stageAttributionStatus: stageAttributionStatus as ParliamentaryTransfer["stageAttributionStatus"],
    collectedAt,
    sourceUrl,
    artifactSha256,
    methodologyVersion: "parliamentary-transfers/1.0.0",
  };
}

async function callRpc(
  name: string,
  body: Record<string, unknown>,
): Promise<unknown[] | null> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return null;
  }
  const response = await fetch(`${supabaseUrl}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: publishableKey,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    next: { revalidate: 300 },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) return null;
  const payload: unknown = await response.json();
  return Array.isArray(payload) ? payload : null;
}

export async function getPublicParliamentaryTransfers(): Promise<ParliamentaryTransfersResult> {
  try {
    const [peopleRows, collectiveRows, transferRows] = await Promise.all([
      callRpc("get_public_parliamentary_transfer_ranking", {
        author_scope: "person",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_parliamentary_transfer_ranking", {
        author_scope: "collective",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_parliamentary_transfers", {
        fiscal_year_filter: null,
        author_kind_filter: null,
        page_size: 200,
      }),
    ]);
    if (!peopleRows || !collectiveRows || !transferRows) return { state: "unavailable" };

    const people = parseRankingRows(peopleRows);
    const collectives = parseRankingRows(collectiveRows);
    const transfers = transferRows.flatMap((row) => {
      if (typeof row !== "object" || row === null) return [];
      const parsed = parseTransfer(row as Record<string, unknown>);
      return parsed ? [parsed] : [];
    });
    return { state: "available", people, collectives, transfers };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicParliamentaryTransferRankings(): Promise<ParliamentaryTransferRankingsResult> {
  try {
    const [peopleRows, collectiveRows] = await Promise.all([
      callRpc("get_public_parliamentary_transfer_ranking", {
        author_scope: "person",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_parliamentary_transfer_ranking", {
        author_scope: "collective",
        fiscal_year_filter: null,
        page_size: 50,
      }),
    ]);
    if (!peopleRows || !collectiveRows) return { state: "unavailable" };
    return {
      state: "available",
      people: parseRankingRows(peopleRows),
      collectives: parseRankingRows(collectiveRows),
    };
  } catch {
    return { state: "unavailable" };
  }
}

export function transferSummaryForRepresentative(
  rows: readonly ParliamentaryTransferRanking[],
  sourceKind: ParliamentaryRepresentativeSourceKind,
  representativeExternalId: string,
): ParliamentaryTransferRanking | null {
  return rows.find(
    (row) => row.associationStatus === "approved_official_crosswalk" &&
      row.representativeSourceKind === sourceKind &&
      row.representativeExternalId === representativeExternalId,
  ) ?? null;
}

export function parliamentaryTransferAuthorAnchor(authorKey: string): string {
  return `autor-${authorKey
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}`;
}
