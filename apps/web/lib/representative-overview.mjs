const DEFAULT_FEDERAL_LIMIT = 10;

function normalizedOffice(value) {
  return typeof value === "string"
    ? value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, " ")
        .trim()
        .toLowerCase()
    : "";
}

function isEligibleFederalVote(vote, currentIds) {
  return vote?.sourceKind === "federal" &&
    currentIds.has(vote.representativeExternalId) &&
    vote.voteScope === "person" &&
    vote.turnNumber === 1 &&
    normalizedOffice(vote.office) === "deputado federal" &&
    Number.isSafeInteger(vote.electionYear) &&
    Number.isSafeInteger(vote.votesInBarreiras) &&
    vote.votesInBarreiras >= 0;
}

export function selectFederalRepresentativesForOverview(
  representatives,
  votes,
  limit = DEFAULT_FEDERAL_LIMIT,
) {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 50) {
    throw new TypeError("limit must be an integer between 1 and 50");
  }

  const currentById = new Map(
    representatives
      .filter((representative) => typeof representative?.externalId === "string")
      .map((representative) => [representative.externalId, representative]),
  );
  const currentIds = new Set(currentById.keys());
  const eligibleVotes = votes.filter((vote) =>
    isEligibleFederalVote(vote, currentIds),
  );
  if (eligibleVotes.length === 0) return [];

  const latestElectionYear = Math.max(
    ...eligibleVotes.map((vote) => vote.electionYear),
  );
  const bestVoteByRepresentative = new Map();
  for (const vote of eligibleVotes) {
    if (vote.electionYear !== latestElectionYear) continue;
    const previous = bestVoteByRepresentative.get(vote.representativeExternalId);
    if (!previous || vote.votesInBarreiras > previous.votesInBarreiras) {
      bestVoteByRepresentative.set(vote.representativeExternalId, vote);
    }
  }

  return [...bestVoteByRepresentative.entries()]
    .map(([externalId, rankingVote]) => ({
      representative: currentById.get(externalId),
      rankingVote,
    }))
    .filter(({ representative }) => representative !== undefined)
    .sort((left, right) =>
      right.rankingVote.votesInBarreiras - left.rankingVote.votesInBarreiras ||
      left.representative.displayName.localeCompare(
        right.representative.displayName,
        "pt-BR",
      ) ||
      left.representative.externalId.localeCompare(right.representative.externalId)
    )
    .slice(0, limit);
}
