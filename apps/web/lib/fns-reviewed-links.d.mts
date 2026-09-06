export type FnsReviewedLink = Readonly<{
  documentCode: string;
  cguArchiveSha256: string;
  requesterName: string;
  fnsAuthorName: string;
  paymentSha256: string;
  orderSha256: string;
  sourceUrl: string;
  reviewedAt: string;
}>;
export type FnsReviewedLinksResult = Readonly<{
  state: "available" | "unavailable";
  links: readonly FnsReviewedLink[];
}>;
export function loadReviewedFnsLinks(
  documents: readonly Readonly<{
    documentCode: string; artifactSha256: string; expenseStage: string;
    authorKind: string; authorName: string;
  }>[],
  callRpc: (codes: readonly string[]) => Promise<unknown>,
): Promise<FnsReviewedLinksResult>;
