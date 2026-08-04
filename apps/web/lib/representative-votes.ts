export type RepresentativeVote = Readonly<{
  sourceKind: "federal" | "state" | "municipal" | "executive";
  representativeExternalId: string;
  electionYear: number;
  turnNumber: number;
  office: string;
  candidateId: string;
  candidateNumber: string | null;
  displayName: string | null;
  ballotName: string | null;
  party: string | null;
  situation: string | null;
  votesInBarreiras: number;
  zones: number;
  collectedAt: string;
  evidenceUrl: string;
  matchMethod: string;
  voteScope: "person" | "ticket";
  scopeNote: string;
  methodologyVersion: string;
}>;

export type RepresentativeVotesResult =
  | Readonly<{ state: "available"; votes: readonly RepresentativeVote[] }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) ? value : null;
}

function parseVote(row: Record<string, unknown>): RepresentativeVote | null {
  const sourceKind = optionalString(row.source_kind);
  const representativeExternalId = optionalString(row.representative_external_id);
  const electionYear = parseInteger(row.election_year);
  const turnNumber = parseInteger(row.turn_number);
  const office = optionalString(row.office);
  const candidateId = optionalString(row.candidate_id);
  const votesInBarreiras = parseInteger(row.votes_in_barreiras);
  const zones = parseInteger(row.zones);
  const collectedAt = optionalString(row.collected_at);
  const evidenceUrl = optionalString(row.evidence_url);
  const voteScope = optionalString(row.vote_scope);
  const scopeNote = optionalString(row.scope_note);
  const methodologyVersion = optionalString(row.methodology_version);
  if (
    sourceKind !== "federal" &&
    sourceKind !== "state" &&
    sourceKind !== "municipal" &&
    sourceKind !== "executive" ||
    representativeExternalId === null ||
    electionYear === null ||
    electionYear < 1900 ||
    turnNumber === null ||
    turnNumber < 1 ||
    office === null ||
    candidateId === null ||
    votesInBarreiras === null ||
    votesInBarreiras < 0 ||
    zones === null ||
    zones < 1 ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    evidenceUrl === null ||
    !evidenceUrl.startsWith("https://") ||
    (methodologyVersion !== "representative-tse-crosswalk/1.0.0" &&
      methodologyVersion !== "representative-tse-crosswalk/1.1.0") ||
    (row.match_method !== "exact_ballot_name_party_office" &&
      row.match_method !== "reviewed_official_alias") ||
    (voteScope !== "person" && voteScope !== "ticket") ||
    scopeNote === null
  ) {
    return null;
  }
  return {
    sourceKind,
    representativeExternalId,
    electionYear,
    turnNumber,
    office,
    candidateId,
    candidateNumber: optionalString(row.candidate_number),
    displayName: optionalString(row.display_name),
    ballotName: optionalString(row.ballot_name),
    party: optionalString(row.party),
    situation: optionalString(row.situation),
    votesInBarreiras,
    zones,
    collectedAt,
    evidenceUrl,
    matchMethod: String(row.match_method),
    voteScope,
    scopeNote,
    methodologyVersion,
  };
}

export async function getRepresentativeVotes(): Promise<RepresentativeVotesResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_representative_tse_votes`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
        next: { revalidate: 900 },
        signal: AbortSignal.timeout(10_000),
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      return { state: "unavailable" };
    }
    const votes: RepresentativeVote[] = [];
    for (const row of payload) {
      const vote = parseVote(row as Record<string, unknown>);
      if (vote === null) {
        return { state: "unavailable" };
      }
      votes.push(vote);
    }
    return { state: "available", votes };
  } catch {
    return { state: "unavailable" };
  }
}

export function votesForRepresentative(
  votes: readonly RepresentativeVote[],
  sourceKind: RepresentativeVote["sourceKind"],
  representativeExternalId: string,
): readonly RepresentativeVote[] {
  return votes.filter(
    (vote) =>
      vote.sourceKind === sourceKind &&
      vote.representativeExternalId === representativeExternalId,
  );
}
