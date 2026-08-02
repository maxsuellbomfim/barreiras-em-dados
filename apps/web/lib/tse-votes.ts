export type TseVote = Readonly<{
  electionYear: number;
  turnNumber: number;
  office: string | null;
  candidateId: string;
  candidateNumber: string | null;
  displayName: string | null;
  ballotName: string | null;
  party: string | null;
  situation: string | null;
  votesInBarreiras: number;
  zones: number;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type TseVotesResult =
  | Readonly<{ state: "available"; votes: readonly TseVote[] }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value)
    ? value
    : null;
}

function parseVote(row: Record<string, unknown>): TseVote | null {
  const electionYear = parseInteger(row.election_year);
  const turnNumber = parseInteger(row.turn_number);
  const candidateId = optionalString(row.candidate_id);
  const votesInBarreiras = parseInteger(row.votes_in_barreiras);
  const zones = parseInteger(row.zones);
  const collectedAt = optionalString(row.collected_at);
  if (
    electionYear === null ||
    electionYear < 1900 ||
    turnNumber === null ||
    turnNumber < 1 ||
    candidateId === null ||
    votesInBarreiras === null ||
    votesInBarreiras < 0 ||
    zones === null ||
    zones < 1 ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== "tse-votes-barreiras/1.0.0"
  ) {
    return null;
  }
  return {
    electionYear,
    turnNumber,
    office: optionalString(row.office),
    candidateId,
    candidateNumber: optionalString(row.candidate_number),
    displayName: optionalString(row.display_name),
    ballotName: optionalString(row.ballot_name),
    party: optionalString(row.party),
    situation: optionalString(row.situation),
    votesInBarreiras,
    zones,
    collectedAt,
    methodologyVersion: "tse-votes-barreiras/1.0.0",
  };
}

export async function getTseBarreirasVotes(): Promise<TseVotesResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
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
      `${supabaseUrl}/rest/v1/rpc/get_tse_barreiras_votes`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 500 }),
        next: { revalidate: 900 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      return { state: "unavailable" };
    }
    const votes: TseVote[] = [];
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
