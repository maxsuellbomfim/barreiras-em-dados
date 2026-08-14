import {
  buildCurrentTransferRankingRequest,
  buildCurrentTransfersRequest,
} from "./parliamentary-transfer-year-filter.mjs";
import {
  parseStateLoaExecutionRows,
  parseStateLoaExecutionSummary,
  type StateLoaExecutionRecord,
  type StateLoaExecutionSummary,
} from "./state-loa-execution.mjs";

export type {
  StateLoaExecutionRecord,
  StateLoaExecutionSummary,
} from "./state-loa-execution.mjs";

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

export type CurrentParliamentaryTransfersResult =
  | Readonly<{
      state: "available";
      transfers: readonly ParliamentaryTransfer[];
    }>
  | Readonly<{ state: "unavailable" }>;

export type ParliamentaryTransferCoverageStatus =
  | "complete"
  | "empty"
  | "partial"
  | "failed"
  | "blocked"
  | "unclassified";

export type ParliamentaryTransferCoverage = Readonly<{
  fiscalYear: number;
  coverageStatus: ParliamentaryTransferCoverageStatus;
  proposalCount: number | null;
  publishedAmendmentCount: number | null;
  lastAttemptedAt: string | null;
  methodologyVersion: "parliamentary-transfer-coverage/1.0.0";
}>;

export type FederalTransferProposal = Readonly<{
  proposalId: string;
  proposalNumber: string | null;
  fiscalYear: number;
  proposalDateText: string | null;
  proposalStatus: string | null;
  basicProjectStatus: string | null;
  modality: string | null;
  objectDescription: string | null;
  investmentItem: string | null;
  proponentName: string | null;
  federalBodyName: string | null;
  superiorFederalBodyName: string | null;
  globalAmount: string | null;
  requestedTransferAmount: string | null;
  counterpartAmount: string | null;
  authorshipStatus: "not_available_in_proposal_source";
  financialStage: "proposal_registered";
  collectedAt: string;
  sourceUrl: string;
  artifactSha256: string;
  methodologyVersion: "federal-transfer-proposals/1.0.0";
}>;

export type HistoricalParliamentaryAmendment = Readonly<{
  externalTransferKey: string;
  proposalId: string;
  proposalNumber: string | null;
  fiscalYear: number;
  amendmentNumber: string | null;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  amendmentKind: string | null;
  programCode: string | null;
  isMandatory: boolean | null;
  destinationAmount: string;
  amendmentTotalInSource: string | null;
  beneficiaryName: string | null;
  objectDescription: string | null;
  proposalStatus: string | null;
  financialStage: "destination_identified_payment_not_verified";
  collectedAt: string;
  sourceUrl: string;
  artifactSha256: string;
  methodologyVersion: "historical-parliamentary-amendments/1.0.0";
}>;

export type HistoricalParliamentaryAmendmentRanking = Readonly<{
  rankPosition: number;
  authorKey: string;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  amendmentCount: number;
  proposalCount: number;
  destinationAmount: string;
  firstYear: number;
  lastYear: number;
  financialStage: "destination_identified_payment_not_verified";
  methodologyVersion: "historical-parliamentary-amendment-ranking/1.0.0";
}>;

export type BahiaStateLoaAmendment = Readonly<{
  fiscalYear: number;
  amendmentNumber: string;
  authorExternalCode: string | null;
  authorKey: string;
  authorName: string;
  authorizedAmount: string;
  officialDescription: string;
  annexCode: string | null;
  budgetUnitCode: string | null;
  agencyCode: string | null;
  actionCode: string | null;
  pageNumber: number;
  evidenceText: string;
  financialStage: "authorized";
  sourceUrl: string;
  sourceArtifactSha256: string;
  evidenceSha256: string;
  methodologyVersion: "bahia-state-loa-amendments/1.0.0";
}>;

export type BahiaStateLoaAmendmentRanking = Readonly<{
  rankPosition: number;
  authorKey: string;
  authorName: string;
  authorExternalCode: string | null;
  representativeSourceKind: ParliamentaryRepresentativeSourceKind | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: Exclude<
    ParliamentaryAuthorAssociationStatus,
    "not_applicable_collective"
  >;
  amendmentCount: number;
  authorizedAmount: string;
  firstYear: number;
  lastYear: number;
  financialStage: "authorized";
  methodologyVersion: "bahia-state-loa-amendment-ranking/1.2.0";
}>;

export type FederalTransferScopeSummary = Readonly<{
  candidateProposalCount: number;
  includedProposalCount: number;
  excludedRegionalProposalCount: number;
  candidateAmendmentCount: number;
  includedAmendmentCount: number;
  excludedRegionalAmendmentCount: number;
  excludedRegionalDestinationAmount: string;
  methodologyVersion: "federal-transfer-territorial-scope/1.0.0";
}>;

export type ReconciledParliamentaryTransfer = Readonly<{
  reconciliationKey: string;
  proposalId: string;
  proposalNumber: string | null;
  fiscalYear: number;
  amendmentNumber: string | null;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  reconciliationStatus:
    | "matched_exact"
    | "current_only"
    | "historical_only"
    | "conflict_non_unique_official_key"
    | "conflict_source_divergence";
  destinationAmount: string | null;
  currentDestinationAmount: string | null;
  historicalDestinationAmount: string | null;
  committedAmount: string | null;
  paidAmount: string | null;
  currentSourceUrl: string | null;
  currentArtifactSha256: string | null;
  historicalSourceUrl: string | null;
  historicalArtifactSha256: string | null;
  methodologyVersion: "reconciled-parliamentary-transfers/1.0.0";
}>;

export type ReconciledParliamentaryTransferRanking = Readonly<{
  rankPosition: number;
  authorKey: string;
  authorName: string;
  authorKind: ParliamentaryAuthorKind;
  representativeSourceKind: ParliamentaryRepresentativeSourceKind | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: ParliamentaryAuthorAssociationStatus;
  amendmentCount: number;
  proposalCount: number;
  destinationAmount: string;
  committedAmount: string | null;
  paidAmount: string | null;
  firstYear: number;
  lastYear: number;
  methodologyVersion: "reconciled-parliamentary-transfer-ranking/1.0.0";
}>;

export type ParliamentaryTransferReconciliationSummary = Readonly<{
  currentSourceRowCount: number;
  historicalSourceRowCount: number;
  consolidatedRowCount: number;
  exactMatchCount: number;
  currentOnlyCount: number;
  historicalOnlyCount: number;
  conflictCount: number;
  rankableRowCount: number;
  publishedDestinationAmount: string;
  methodologyVersion: "parliamentary-transfer-reconciliation/1.0.0";
}>;

export type ParliamentaryTransfersResult =
  | Readonly<{
      state: "available";
      people: readonly ParliamentaryTransferRanking[];
      collectives: readonly ParliamentaryTransferRanking[];
      transfers: readonly ParliamentaryTransfer[];
      coverage: readonly ParliamentaryTransferCoverage[] | null;
      historicalProposals: readonly FederalTransferProposal[] | null;
      historicalAmendments: readonly HistoricalParliamentaryAmendment[] | null;
      historicalPeople: readonly HistoricalParliamentaryAmendmentRanking[] | null;
      historicalCollectives: readonly HistoricalParliamentaryAmendmentRanking[] | null;
      stateLoaAmendments: readonly BahiaStateLoaAmendment[] | null;
      stateLoaRanking: readonly BahiaStateLoaAmendmentRanking[] | null;
      stateLoaExecution: readonly StateLoaExecutionRecord[] | null;
      stateLoaExecutionSummary: StateLoaExecutionSummary | null;
      scopeSummary: FederalTransferScopeSummary | null;
      reconciledTransfers: readonly ReconciledParliamentaryTransfer[] | null;
      reconciledPeople: readonly ReconciledParliamentaryTransferRanking[] | null;
      reconciledCollectives: readonly ReconciledParliamentaryTransferRanking[] | null;
      reconciliationSummary: ParliamentaryTransferReconciliationSummary | null;
    }>
  | Readonly<{ state: "unavailable" }>;

const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SOURCE_DATE = /^\d{2}\/\d{2}\/\d{4}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const AUTHOR_KINDS = new Set<ParliamentaryAuthorKind>([
  "person",
  "commission",
  "bench",
  "collective",
  "other",
]);
const COVERAGE_STATUSES = new Set<ParliamentaryTransferCoverageStatus>([
  "complete",
  "empty",
  "partial",
  "failed",
  "blocked",
  "unclassified",
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

function parseCoverage(
  row: Record<string, unknown>,
): ParliamentaryTransferCoverage | null {
  const fiscalYear = integer(row.fiscal_year, 2021);
  const status = row.coverage_status;
  const proposalCount = row.proposal_count === null
    ? null
    : integer(row.proposal_count);
  const publishedAmendmentCount = row.published_amendment_count === null
    ? null
    : integer(row.published_amendment_count);
  const lastAttemptedAt = optionalText(row.last_attempted_at);
  const finalStatus = status === "complete" || status === "empty";
  if (
    fiscalYear === null || typeof status !== "string" ||
    !COVERAGE_STATUSES.has(status as ParliamentaryTransferCoverageStatus) ||
    (row.proposal_count !== null && proposalCount === null) ||
    (row.published_amendment_count !== null && publishedAmendmentCount === null) ||
    (lastAttemptedAt !== null && Number.isNaN(Date.parse(lastAttemptedAt))) ||
    (finalStatus && (proposalCount === null || publishedAmendmentCount === null)) ||
    (!finalStatus && (proposalCount !== null || publishedAmendmentCount !== null)) ||
    (status === "empty" && (proposalCount !== 0 || publishedAmendmentCount !== 0)) ||
    row.methodology_version !== "parliamentary-transfer-coverage/1.0.0"
  ) return null;
  return {
    fiscalYear,
    coverageStatus: status as ParliamentaryTransferCoverageStatus,
    proposalCount,
    publishedAmendmentCount,
    lastAttemptedAt,
    methodologyVersion: "parliamentary-transfer-coverage/1.0.0",
  };
}

function parseCoverageRows(
  rows: unknown[],
): ParliamentaryTransferCoverage[] | null {
  const parsed = rows.map((row) => {
    if (typeof row !== "object" || row === null) return null;
    return parseCoverage(row as Record<string, unknown>);
  });
  if (parsed.some((row) => row === null)) return null;
  const coverage = parsed as ParliamentaryTransferCoverage[];
  if (new Set(coverage.map((row) => row.fiscalYear)).size !== coverage.length) {
    return null;
  }
  return coverage.sort((left, right) => right.fiscalYear - left.fiscalYear);
}

function parseFederalTransferProposal(
  row: Record<string, unknown>,
): FederalTransferProposal | null {
  const proposalId = requiredText(row.proposal_id);
  const proposalNumber = optionalText(row.proposal_number);
  const fiscalYear = integer(row.fiscal_year, 2021);
  const proposalDateText = optionalText(row.proposal_date_text);
  const globalAmount = row.global_amount === null ? null : decimal(row.global_amount);
  const requestedTransferAmount = row.requested_transfer_amount === null
    ? null
    : decimal(row.requested_transfer_amount);
  const counterpartAmount = row.counterpart_amount === null
    ? null
    : decimal(row.counterpart_amount);
  const collectedAt = requiredText(row.collected_at);
  const sourceUrl = requiredText(row.source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  if (
    !proposalId || !/^\d+$/.test(proposalId) || fiscalYear === null ||
    (proposalDateText !== null && !SOURCE_DATE.test(proposalDateText)) ||
    (row.global_amount !== null && globalAmount === null) ||
    (row.requested_transfer_amount !== null && requestedTransferAmount === null) ||
    (row.counterpart_amount !== null && counterpartAmount === null) ||
    row.authorship_status !== "not_available_in_proposal_source" ||
    row.financial_stage !== "proposal_registered" ||
    !collectedAt || Number.isNaN(Date.parse(collectedAt)) ||
    !sourceUrl?.startsWith("https://") || !artifactSha256 ||
    !SHA256.test(artifactSha256) ||
    row.methodology_version !== "federal-transfer-proposals/1.0.0"
  ) return null;
  return {
    proposalId,
    proposalNumber,
    fiscalYear,
    proposalDateText,
    proposalStatus: optionalText(row.proposal_status),
    basicProjectStatus: optionalText(row.basic_project_status),
    modality: optionalText(row.modality),
    objectDescription: optionalText(row.object_description),
    investmentItem: optionalText(row.investment_item),
    proponentName: optionalText(row.proponent_name),
    federalBodyName: optionalText(row.federal_body_name),
    superiorFederalBodyName: optionalText(row.superior_federal_body_name),
    globalAmount,
    requestedTransferAmount,
    counterpartAmount,
    authorshipStatus: "not_available_in_proposal_source",
    financialStage: "proposal_registered",
    collectedAt,
    sourceUrl,
    artifactSha256,
    methodologyVersion: "federal-transfer-proposals/1.0.0",
  };
}

function parseFederalTransferProposalRows(
  rows: unknown[],
): FederalTransferProposal[] | null {
  const parsed = rows.map((row) => {
    if (typeof row !== "object" || row === null) return null;
    return parseFederalTransferProposal(row as Record<string, unknown>);
  });
  if (parsed.some((row) => row === null)) return null;
  const proposals = parsed as FederalTransferProposal[];
  if (new Set(proposals.map((row) => row.proposalId)).size !== proposals.length) {
    return null;
  }
  return proposals;
}

function parseHistoricalAmendment(
  row: Record<string, unknown>,
): HistoricalParliamentaryAmendment | null {
  const externalTransferKey = requiredText(row.external_transfer_key);
  const proposalId = requiredText(row.proposal_id);
  const fiscalYear = integer(row.fiscal_year, 2021);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const destinationAmount = decimal(row.destination_amount);
  const amendmentTotalInSource = row.amendment_total_in_source === null
    ? null
    : decimal(row.amendment_total_in_source);
  const collectedAt = requiredText(row.collected_at);
  const sourceUrl = requiredText(row.source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const isMandatory = row.is_mandatory;
  if (
    !externalTransferKey || !proposalId || !/^\d+$/.test(proposalId) ||
    fiscalYear === null || !authorName || !kind || !destinationAmount ||
    (row.amendment_total_in_source !== null && amendmentTotalInSource === null) ||
    ![true, false, null].includes(isMandatory as boolean | null) ||
    row.financial_stage !== "destination_identified_payment_not_verified" ||
    !collectedAt || Number.isNaN(Date.parse(collectedAt)) ||
    !sourceUrl?.startsWith("https://") || !artifactSha256 ||
    !SHA256.test(artifactSha256) ||
    row.methodology_version !== "historical-parliamentary-amendments/1.0.0"
  ) return null;
  return {
    externalTransferKey,
    proposalId,
    proposalNumber: optionalText(row.proposal_number),
    fiscalYear,
    amendmentNumber: optionalText(row.amendment_number),
    authorName,
    authorKind: kind,
    amendmentKind: optionalText(row.amendment_kind),
    programCode: optionalText(row.program_code),
    isMandatory: isMandatory as boolean | null,
    destinationAmount,
    amendmentTotalInSource,
    beneficiaryName: optionalText(row.beneficiary_name),
    objectDescription: optionalText(row.object_description),
    proposalStatus: optionalText(row.proposal_status),
    financialStage: "destination_identified_payment_not_verified",
    collectedAt,
    sourceUrl,
    artifactSha256,
    methodologyVersion: "historical-parliamentary-amendments/1.0.0",
  };
}

function parseHistoricalAmendmentRows(
  rows: unknown[],
): HistoricalParliamentaryAmendment[] | null {
  const parsed = rows.map((row) => {
    if (typeof row !== "object" || row === null) return null;
    return parseHistoricalAmendment(row as Record<string, unknown>);
  });
  if (parsed.some((row) => row === null)) return null;
  const amendments = parsed as HistoricalParliamentaryAmendment[];
  if (
    new Set(amendments.map((row) => row.externalTransferKey)).size !==
    amendments.length
  ) return null;
  return amendments;
}

function parseHistoricalRanking(
  row: Record<string, unknown>,
): HistoricalParliamentaryAmendmentRanking | null {
  const rankPosition = integer(row.rank_position, 1);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const amendmentCount = integer(row.amendment_count);
  const proposalCount = integer(row.proposal_count);
  const destinationAmount = decimal(row.destination_amount);
  const firstYear = integer(row.first_year, 2021);
  const lastYear = integer(row.last_year, 2021);
  if (
    rankPosition === null || !authorKey || !authorName || !kind ||
    amendmentCount === null || proposalCount === null || !destinationAmount ||
    firstYear === null || lastYear === null || firstYear > lastYear ||
    row.financial_stage !== "destination_identified_payment_not_verified" ||
    row.methodology_version !==
      "historical-parliamentary-amendment-ranking/1.0.0"
  ) return null;
  return {
    rankPosition,
    authorKey,
    authorName,
    authorKind: kind,
    amendmentCount,
    proposalCount,
    destinationAmount,
    firstYear,
    lastYear,
    financialStage: "destination_identified_payment_not_verified",
    methodologyVersion: "historical-parliamentary-amendment-ranking/1.0.0",
  };
}

function parseHistoricalRankingRows(
  rows: unknown[],
): HistoricalParliamentaryAmendmentRanking[] | null {
  const parsed = rows.map((row) => {
    if (typeof row !== "object" || row === null) return null;
    return parseHistoricalRanking(row as Record<string, unknown>);
  });
  return parsed.some((row) => row === null)
    ? null
    : parsed as HistoricalParliamentaryAmendmentRanking[];
}

function parseBahiaStateLoaAmendment(
  row: Record<string, unknown>,
): BahiaStateLoaAmendment | null {
  const fiscalYear = integer(row.fiscal_year, 2022);
  const amendmentNumber = requiredText(row.amendment_number);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const authorizedAmount = decimal(row.authorized_amount);
  const officialDescription = requiredText(row.official_description);
  const pageNumber = integer(row.page_number, 1);
  const evidenceText = requiredText(row.evidence_text);
  const sourceUrl = requiredText(row.source_url);
  const sourceArtifactSha256 = requiredText(row.source_artifact_sha256);
  const evidenceSha256 = requiredText(row.evidence_sha256);
  if (
    fiscalYear === null || !amendmentNumber || !authorKey || !authorName ||
    !authorizedAmount || !officialDescription || pageNumber === null ||
    !evidenceText || !sourceUrl?.startsWith("https://") ||
    !sourceArtifactSha256 || !SHA256.test(sourceArtifactSha256) ||
    !evidenceSha256 || !SHA256.test(evidenceSha256) ||
    row.financial_stage !== "authorized" ||
    row.methodology_version !== "bahia-state-loa-amendments/1.0.0"
  ) return null;
  return {
    fiscalYear,
    amendmentNumber,
    authorExternalCode: optionalText(row.author_external_code),
    authorKey,
    authorName,
    authorizedAmount,
    officialDescription,
    annexCode: optionalText(row.annex_code),
    budgetUnitCode: optionalText(row.budget_unit_code),
    agencyCode: optionalText(row.agency_code),
    actionCode: optionalText(row.action_code),
    pageNumber,
    evidenceText,
    financialStage: "authorized",
    sourceUrl,
    sourceArtifactSha256,
    evidenceSha256,
    methodologyVersion: "bahia-state-loa-amendments/1.0.0",
  };
}

function parseBahiaStateLoaRanking(
  row: Record<string, unknown>,
): BahiaStateLoaAmendmentRanking | null {
  const rankPosition = integer(row.rank_position, 1);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const representativeSourceKind = optionalText(row.representative_source_kind);
  const representativeExternalId = optionalText(row.representative_external_id);
  const representativeProfileUrl = optionalText(row.representative_profile_url);
  const associationStatus = optionalText(row.association_status);
  const amendmentCount = integer(row.amendment_count, 1);
  const authorizedAmount = decimal(row.authorized_amount);
  const firstYear = integer(row.first_year, 2022);
  const lastYear = integer(row.last_year, 2022);
  if (
    rankPosition === null || !authorKey || !authorName || amendmentCount === null ||
    !authorizedAmount || firstYear === null || lastYear === null || firstYear > lastYear ||
    !["approved_official_crosswalk", "not_linked"].includes(associationStatus ?? "") ||
    (associationStatus === "approved_official_crosswalk" && (
      !representativeSourceKind || !["federal", "state"].includes(representativeSourceKind) ||
      !representativeExternalId || !representativeProfileUrl ||
      (representativeSourceKind === "state" &&
        !representativeProfileUrl.startsWith("https://www.al.ba.gov.br/")) ||
      (representativeSourceKind === "federal" &&
        !representativeProfileUrl.startsWith("https://www.camara.leg.br/"))
    )) ||
    (associationStatus === "not_linked" && (
      representativeSourceKind !== null || representativeExternalId !== null ||
      representativeProfileUrl !== null
    )) ||
    row.financial_stage !== "authorized" ||
    row.methodology_version !== "bahia-state-loa-amendment-ranking/1.2.0"
  ) return null;
  return {
    rankPosition,
    authorKey,
    authorName,
    authorExternalCode: optionalText(row.author_external_code),
    representativeSourceKind:
      representativeSourceKind as ParliamentaryRepresentativeSourceKind | null,
    representativeExternalId,
    representativeProfileUrl,
    associationStatus: associationStatus as Exclude<
      ParliamentaryAuthorAssociationStatus,
      "not_applicable_collective"
    >,
    amendmentCount,
    authorizedAmount,
    firstYear,
    lastYear,
    financialStage: "authorized",
    methodologyVersion: "bahia-state-loa-amendment-ranking/1.2.0",
  };
}

function parseBahiaStateLoaRows<T>(
  rows: unknown[],
  parser: (row: Record<string, unknown>) => T | null,
): T[] | null {
  const parsed = rows.map((row) => {
    if (typeof row !== "object" || row === null) return null;
    return parser(row as Record<string, unknown>);
  });
  return parsed.some((row) => row === null) ? null : parsed as T[];
}

function parseScopeSummary(rows: unknown[]): FederalTransferScopeSummary | null {
  if (rows.length !== 1 || typeof rows[0] !== "object" || rows[0] === null) return null;
  const row = rows[0] as Record<string, unknown>;
  const candidateProposalCount = integer(row.candidate_proposal_count);
  const includedProposalCount = integer(row.included_proposal_count);
  const excludedRegionalProposalCount = integer(row.excluded_regional_proposal_count);
  const candidateAmendmentCount = integer(row.candidate_amendment_count);
  const includedAmendmentCount = integer(row.included_amendment_count);
  const excludedRegionalAmendmentCount = integer(row.excluded_regional_amendment_count);
  const excludedRegionalDestinationAmount = decimal(
    row.excluded_regional_destination_amount,
  );
  if (
    candidateProposalCount === null || includedProposalCount === null ||
    excludedRegionalProposalCount === null || candidateAmendmentCount === null ||
    includedAmendmentCount === null || excludedRegionalAmendmentCount === null ||
    excludedRegionalDestinationAmount === null ||
    includedProposalCount + excludedRegionalProposalCount !== candidateProposalCount ||
    includedAmendmentCount + excludedRegionalAmendmentCount !== candidateAmendmentCount ||
    row.methodology_version !== "federal-transfer-territorial-scope/1.0.0"
  ) return null;
  return {
    candidateProposalCount,
    includedProposalCount,
    excludedRegionalProposalCount,
    candidateAmendmentCount,
    includedAmendmentCount,
    excludedRegionalAmendmentCount,
    excludedRegionalDestinationAmount,
    methodologyVersion: "federal-transfer-territorial-scope/1.0.0",
  };
}

const RECONCILIATION_STATUSES = new Set<
  ReconciledParliamentaryTransfer["reconciliationStatus"]
>([
  "matched_exact",
  "current_only",
  "historical_only",
  "conflict_non_unique_official_key",
  "conflict_source_divergence",
]);

function parseReconciledTransfer(
  row: Record<string, unknown>,
): ReconciledParliamentaryTransfer | null {
  const reconciliationKey = requiredText(row.reconciliation_key);
  const proposalId = requiredText(row.proposal_id);
  const fiscalYear = integer(row.fiscal_year, 2021);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const status = optionalText(row.reconciliation_status);
  const nullableDecimal = (value: unknown) => value === null ? null : decimal(value);
  const destinationAmount = nullableDecimal(row.destination_amount);
  const currentDestinationAmount = nullableDecimal(row.current_destination_amount);
  const historicalDestinationAmount = nullableDecimal(row.historical_destination_amount);
  const committedAmount = nullableDecimal(row.committed_amount);
  const paidAmount = nullableDecimal(row.paid_amount);
  const currentSourceUrl = optionalText(row.current_source_url);
  const currentArtifactSha256 = optionalText(row.current_artifact_sha256);
  const historicalSourceUrl = optionalText(row.historical_source_url);
  const historicalArtifactSha256 = optionalText(row.historical_artifact_sha256);
  if (
    !reconciliationKey || !proposalId || fiscalYear === null || !authorName || !kind ||
    !status || !RECONCILIATION_STATUSES.has(
      status as ReconciledParliamentaryTransfer["reconciliationStatus"],
    ) ||
    (row.destination_amount !== null && destinationAmount === null) ||
    (row.current_destination_amount !== null && currentDestinationAmount === null) ||
    (row.historical_destination_amount !== null && historicalDestinationAmount === null) ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null) ||
    (currentSourceUrl !== null && !currentSourceUrl.startsWith("https://")) ||
    (historicalSourceUrl !== null && !historicalSourceUrl.startsWith("https://")) ||
    (currentArtifactSha256 !== null && !SHA256.test(currentArtifactSha256)) ||
    (historicalArtifactSha256 !== null && !SHA256.test(historicalArtifactSha256)) ||
    row.methodology_version !== "reconciled-parliamentary-transfers/1.0.0"
  ) return null;
  return {
    reconciliationKey,
    proposalId,
    proposalNumber: optionalText(row.proposal_number),
    fiscalYear,
    amendmentNumber: optionalText(row.amendment_number),
    authorName,
    authorKind: kind,
    reconciliationStatus:
      status as ReconciledParliamentaryTransfer["reconciliationStatus"],
    destinationAmount,
    currentDestinationAmount,
    historicalDestinationAmount,
    committedAmount,
    paidAmount,
    currentSourceUrl,
    currentArtifactSha256,
    historicalSourceUrl,
    historicalArtifactSha256,
    methodologyVersion: "reconciled-parliamentary-transfers/1.0.0",
  };
}

function parseReconciledRanking(
  row: Record<string, unknown>,
): ReconciledParliamentaryTransferRanking | null {
  const rankPosition = integer(row.rank_position, 1);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const kind = authorKind(row.author_kind);
  const amendmentCount = integer(row.amendment_count);
  const proposalCount = integer(row.proposal_count);
  const destinationAmount = decimal(row.destination_amount);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const firstYear = integer(row.first_year, 2021);
  const lastYear = integer(row.last_year, 2021);
  const sourceKind = optionalText(row.representative_source_kind);
  const associationStatus = optionalText(row.association_status);
  if (
    rankPosition === null || !authorKey || !authorName || !kind ||
    amendmentCount === null || proposalCount === null || !destinationAmount ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null) ||
    firstYear === null || lastYear === null || firstYear > lastYear ||
    (sourceKind !== null && !["federal", "state"].includes(sourceKind)) ||
    !associationStatus || ![
      "approved_official_crosswalk", "not_linked", "not_applicable_collective",
    ].includes(associationStatus) ||
    row.methodology_version !==
      "reconciled-parliamentary-transfer-ranking/1.0.0"
  ) return null;
  return {
    rankPosition,
    authorKey,
    authorName,
    authorKind: kind,
    representativeSourceKind:
      sourceKind as ParliamentaryRepresentativeSourceKind | null,
    representativeExternalId: optionalText(row.representative_external_id),
    representativeProfileUrl: optionalText(row.representative_profile_url),
    associationStatus: associationStatus as ParliamentaryAuthorAssociationStatus,
    amendmentCount,
    proposalCount,
    destinationAmount,
    committedAmount,
    paidAmount,
    firstYear,
    lastYear,
    methodologyVersion: "reconciled-parliamentary-transfer-ranking/1.0.0",
  };
}

function parseReconciliationSummary(
  rows: unknown[],
): ParliamentaryTransferReconciliationSummary | null {
  if (rows.length !== 1 || typeof rows[0] !== "object" || rows[0] === null) return null;
  const row = rows[0] as Record<string, unknown>;
  const values = [
    row.current_source_row_count,
    row.historical_source_row_count,
    row.consolidated_row_count,
    row.exact_match_count,
    row.current_only_count,
    row.historical_only_count,
    row.conflict_count,
    row.rankable_row_count,
  ].map((value) => integer(value));
  const publishedDestinationAmount = decimal(row.published_destination_amount);
  if (
    values.some((value) => value === null) || !publishedDestinationAmount ||
    row.methodology_version !== "parliamentary-transfer-reconciliation/1.0.0"
  ) return null;
  const [currentSourceRowCount, historicalSourceRowCount, consolidatedRowCount,
    exactMatchCount, currentOnlyCount, historicalOnlyCount, conflictCount,
    rankableRowCount] = values as number[];
  if (
    exactMatchCount + currentOnlyCount + historicalOnlyCount + conflictCount !==
      consolidatedRowCount ||
    rankableRowCount + conflictCount !== consolidatedRowCount
  ) return null;
  return {
    currentSourceRowCount,
    historicalSourceRowCount,
    consolidatedRowCount,
    exactMatchCount,
    currentOnlyCount,
    historicalOnlyCount,
    conflictCount,
    rankableRowCount,
    publishedDestinationAmount,
    methodologyVersion: "parliamentary-transfer-reconciliation/1.0.0",
  };
}

type RpcRequest = Readonly<{
  headers: Readonly<Record<string, string>>;
  body: string;
}>;

async function fetchRpcResponse(
  url: string,
  request: RpcRequest,
  bypassCache = false,
): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: request.headers,
    body: request.body,
    ...(bypassCache ? { cache: "no-store" as const } : { next: { revalidate: 300 } }),
    signal: AbortSignal.timeout(5_000),
  });
}

function isTransientRpcFailure(response: Response): boolean {
  return [404, 408, 425, 429].includes(response.status) || response.status >= 500;
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
  const url = `${supabaseUrl}/rest/v1/rpc/${name}`;
  const request: RpcRequest = {
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: publishableKey,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  };
  const cachedResponse = await fetchRpcResponse(url, request);
  const response = !cachedResponse.ok && isTransientRpcFailure(cachedResponse)
    ? await fetchRpcResponse(url, request, true)
    : cachedResponse;
  if (!response.ok) return null;
  const payload: unknown = await response.json();
  return Array.isArray(payload) ? payload : null;
}

export async function getPublicParliamentaryTransfers({
  stateFiscalYear,
}: Readonly<{
  stateFiscalYear: number;
}>): Promise<ParliamentaryTransfersResult> {
  try {
    const [
      peopleRows,
      collectiveRows,
      transferRows,
      coverageRows,
      historicalProposalRows,
      historicalAmendmentRows,
      historicalPeopleRows,
      historicalCollectiveRows,
      stateLoaAmendmentRows,
      stateLoaRankingRows,
      stateLoaExecutionRows,
      stateLoaExecutionSummaryRows,
      scopeSummaryRows,
      reconciledTransferRows,
      reconciledPeopleRows,
      reconciledCollectiveRows,
      reconciliationSummaryRows,
    ] = await Promise.all([
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
      callRpc("get_public_parliamentary_transfer_coverage", {
        fiscal_year_from: 2021,
      }),
      callRpc("get_public_federal_transfer_proposals", {
        fiscal_year_filter: null,
        proposal_status_filter: null,
        page_size: 200,
      }),
      callRpc("get_public_historical_parliamentary_amendments", {
        fiscal_year_filter: null,
        author_kind_filter: null,
        page_size: 200,
      }),
      callRpc("get_public_historical_parliamentary_amendment_ranking", {
        author_scope: "person",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_historical_parliamentary_amendment_ranking", {
        author_scope: "collective",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_bahia_state_loa_amendments", {
        fiscal_year_filter: stateFiscalYear,
        author_key_filter: null,
        page_size: 200,
      }),
      callRpc("get_public_bahia_state_loa_amendment_ranking", {
        fiscal_year_filter: stateFiscalYear,
        page_size: 50,
      }),
      callRpc("get_public_bahia_state_loa_execution", {
        fiscal_year_filter: stateFiscalYear,
        author_key_filter: null,
        page_size: 200,
      }),
      callRpc("get_public_bahia_state_loa_execution_summary", {
        fiscal_year_filter: stateFiscalYear,
      }),
      callRpc("get_public_federal_transfer_scope_summary", {}),
      callRpc("get_public_reconciled_parliamentary_transfers", {
        fiscal_year_filter: null,
        author_kind_filter: null,
        page_size: 200,
      }),
      callRpc("get_public_reconciled_parliamentary_transfer_ranking", {
        author_scope: "person",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_reconciled_parliamentary_transfer_ranking", {
        author_scope: "collective",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc("get_public_parliamentary_transfer_reconciliation_summary", {}),
    ]);
    if (!peopleRows || !collectiveRows || !transferRows) return { state: "unavailable" };

    const people = parseRankingRows(peopleRows);
    const collectives = parseRankingRows(collectiveRows);
    const transfers = transferRows.flatMap((row) => {
      if (typeof row !== "object" || row === null) return [];
      const parsed = parseTransfer(row as Record<string, unknown>);
      return parsed ? [parsed] : [];
    });
    const coverage = coverageRows === null ? null : parseCoverageRows(coverageRows);
    const historicalProposals = historicalProposalRows === null
      ? null
      : parseFederalTransferProposalRows(historicalProposalRows);
    const historicalAmendments = historicalAmendmentRows === null
      ? null
      : parseHistoricalAmendmentRows(historicalAmendmentRows);
    const historicalPeople = historicalPeopleRows === null
      ? null
      : parseHistoricalRankingRows(historicalPeopleRows);
    const historicalCollectives = historicalCollectiveRows === null
      ? null
      : parseHistoricalRankingRows(historicalCollectiveRows);
    const stateLoaAmendments = stateLoaAmendmentRows === null
      ? null
      : parseBahiaStateLoaRows(
          stateLoaAmendmentRows,
          parseBahiaStateLoaAmendment,
        );
    const stateLoaRanking = stateLoaRankingRows === null
      ? null
      : parseBahiaStateLoaRows(stateLoaRankingRows, parseBahiaStateLoaRanking);
    const stateLoaExecution = stateLoaExecutionRows === null
      ? null
      : parseStateLoaExecutionRows(stateLoaExecutionRows);
    const stateLoaExecutionSummary = stateLoaExecutionSummaryRows === null
      ? null
      : parseStateLoaExecutionSummary(stateLoaExecutionSummaryRows);
    const scopeSummary = scopeSummaryRows === null
      ? null
      : parseScopeSummary(scopeSummaryRows);
    const reconciledTransfers = reconciledTransferRows === null
      ? null
      : reconciledTransferRows.map((row) => {
        if (typeof row !== "object" || row === null) return null;
        return parseReconciledTransfer(row as Record<string, unknown>);
      });
    const reconciledPeople = reconciledPeopleRows === null
      ? null
      : reconciledPeopleRows.map((row) => {
        if (typeof row !== "object" || row === null) return null;
        return parseReconciledRanking(row as Record<string, unknown>);
      });
    const reconciledCollectives = reconciledCollectiveRows === null
      ? null
      : reconciledCollectiveRows.map((row) => {
        if (typeof row !== "object" || row === null) return null;
        return parseReconciledRanking(row as Record<string, unknown>);
      });
    const reconciliationSummary = reconciliationSummaryRows === null
      ? null
      : parseReconciliationSummary(reconciliationSummaryRows);
    return {
      state: "available",
      people,
      collectives,
      transfers,
      coverage,
      historicalProposals,
      historicalAmendments,
      historicalPeople,
      historicalCollectives,
      stateLoaAmendments,
      stateLoaRanking,
      stateLoaExecution,
      stateLoaExecutionSummary,
      scopeSummary,
      reconciledTransfers: reconciledTransfers?.some((row) => row === null)
        ? null
        : reconciledTransfers as readonly ReconciledParliamentaryTransfer[] | null,
      reconciledPeople: reconciledPeople?.some((row) => row === null)
        ? null
        : reconciledPeople as readonly ReconciledParliamentaryTransferRanking[] | null,
      reconciledCollectives: reconciledCollectives?.some((row) => row === null)
        ? null
        : reconciledCollectives as readonly ReconciledParliamentaryTransferRanking[] | null,
      reconciliationSummary,
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicParliamentaryTransferRankings(
  fiscalYear: number | null = null,
): Promise<ParliamentaryTransferRankingsResult> {
  try {
    const [peopleRows, collectiveRows] = await Promise.all([
      callRpc(
        "get_public_parliamentary_transfer_ranking",
        buildCurrentTransferRankingRequest("person", fiscalYear),
      ),
      callRpc(
        "get_public_parliamentary_transfer_ranking",
        buildCurrentTransferRankingRequest("collective", fiscalYear),
      ),
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

export async function getPublicCurrentParliamentaryTransfers(
  fiscalYear: number,
): Promise<CurrentParliamentaryTransfersResult> {
  try {
    const rows = await callRpc(
      "get_public_parliamentary_transfers",
      buildCurrentTransfersRequest(fiscalYear),
    );
    if (rows === null) return { state: "unavailable" };
    return {
      state: "available",
      transfers: rows.flatMap((row) => {
        if (typeof row !== "object" || row === null) return [];
        const parsed = parseTransfer(row as Record<string, unknown>);
        return parsed ? [parsed] : [];
      }),
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
