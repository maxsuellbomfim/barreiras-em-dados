import type { FederalRepresentative } from "./representatives";
import type { RepresentativeVote } from "./representative-votes";
import type { StateRepresentative } from "./state-representatives";

export type FederalRepresentativeOverviewItem = Readonly<{
  representative: FederalRepresentative;
  rankingVote: RepresentativeVote;
}>;

export function selectFederalRepresentativesForOverview(
  representatives: readonly FederalRepresentative[],
  votes: readonly RepresentativeVote[],
  limit?: number,
): readonly FederalRepresentativeOverviewItem[];

export type StateRepresentativeOverviewItem = Readonly<{
  representative: StateRepresentative;
  rankingVote: RepresentativeVote;
}>;

export function selectStateRepresentativesForOverview(
  representatives: readonly StateRepresentative[],
  votes: readonly RepresentativeVote[],
  limit?: number,
): readonly StateRepresentativeOverviewItem[];
