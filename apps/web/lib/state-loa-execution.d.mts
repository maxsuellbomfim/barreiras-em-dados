import type {
  StateLoaExecutionPublicStatus,
} from "./state-loa-execution-citizen-copy.mjs";

export type StateLoaExecutionRecord = Readonly<{
  fiscalYear: number;
  amendmentNumber: string;
  authorExternalCode: string | null;
  authorKey: string;
  authorName: string;
  authorizedAmount: string;
  officialDescription: string;
  pageNumber: number;
  loaEvidenceText: string;
  loaSourceUrl: string;
  loaSourceArtifactSha256: string;
  loaEvidenceSha256: string;
  executionStatus: StateLoaExecutionPublicStatus;
  loaScopeOccurrences: number;
  executionOccurrences: number;
  committedAmount: string | null;
  liquidatedAmount: string | null;
  paidAmount: string | null;
  executionSourceUrl: string | null;
  executionSourceArtifactSha256: string | null;
  executionEvidenceSha256: string | null;
  executionSourceCollectedAt: string | null;
  methodologyVersion: "bahia-state-loa-public-execution/1.1.0";
}>;

export type StateLoaExecutionSummary = Readonly<{
  fiscalYear: number;
  totalAmendmentCount: number;
  matchedAmendmentCount: number;
  ambiguousAmendmentCount: number;
  notFoundAmendmentCount: number;
  unavailableScopeCount: number;
  authorizedTotal: string;
  matchedAuthorizedTotal: string | null;
  committedTotal: string | null;
  liquidatedTotal: string | null;
  paidTotal: string | null;
  methodologyVersion: "bahia-state-loa-public-execution-summary/1.0.0";
}>;

export function parseStateLoaExecutionRows(
  rows: unknown,
): StateLoaExecutionRecord[] | null;

export function parseStateLoaExecutionSummary(
  rows: unknown,
): StateLoaExecutionSummary | null;
