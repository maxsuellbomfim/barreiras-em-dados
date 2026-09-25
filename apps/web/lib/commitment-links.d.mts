export type CommitmentLink = Readonly<{
  linkId: string;
  contractPortalId: string;
  commitmentKey: string;
  commitmentNumber: string;
  issueDateText: string;
  publicBody: string;
  creditorName: string;
  noteType: string;
  amountText: string;
  citedExcerpt: string;
  ruleVersion: string;
  gridArtifactSha256: string;
  gridRetrievedAt: string;
  sourcePageUrl: string;
  reviewMode: "automated" | "human";
}>;

export function parseCommitmentLinkRows(
  rows: unknown,
): readonly CommitmentLink[] | null;

export function groupLinksByContract(
  links: readonly CommitmentLink[],
): ReadonlyMap<string, readonly CommitmentLink[]>;
