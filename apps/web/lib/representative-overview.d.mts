import type { FederalRepresentative } from "./representatives";
import type { RepresentativeVote } from "./representative-votes";

export type FederalRepresentativeOverviewItem = Readonly<{
  representative: FederalRepresentative;
  rankingVote: RepresentativeVote;
}>;

export function selectFederalRepresentativesForOverview(
  representatives: readonly FederalRepresentative[],
  votes: readonly RepresentativeVote[],
  limit?: number,
): readonly FederalRepresentativeOverviewItem[];
