export type ContestationStatus =
  | "received"
  | "under_review"
  | "upheld"
  | "rejected"
  | "withdrawn";

export type SubmitResult =
  | Readonly<{ state: "created"; protocol: string }>
  | Readonly<{ state: "invalid"; message: string }>
  | Readonly<{ state: "unavailable" }>;

export type ContestationLookup =
  | Readonly<{
      state: "found";
      protocol: string;
      targetPath: string;
      status: ContestationStatus;
      resolutionNote: string | null;
      createdAt: string;
      resolvedAt: string | null;
    }>
  | Readonly<{ state: "not_found" }>
  | Readonly<{ state: "unavailable" }>;

export const STATUS_LABELS: Readonly<Record<ContestationStatus, string>>;

export function normalizeTargetPath(value: unknown): string | null;

export function normalizeProtocol(value: unknown): string | null;

export function submitContestation(input: Readonly<{
  targetPath: string;
  description: string;
  evidenceUrl?: string | null;
  contact?: string | null;
}>): Promise<SubmitResult>;

export function parseContestationRows(
  rows: unknown,
): Exclude<ContestationLookup, Readonly<{ state: "unavailable" }>> | null;

export function getContestation(protocol: string): Promise<ContestationLookup>;
