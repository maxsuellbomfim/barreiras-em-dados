import { fetchPublicRpcRows } from "./public-rpc.mjs";

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
  methodologyVersion: "tse-votes-barreiras/1.0.0";
}>;

export type TseVoteOutcome =
  | "elected"
  | "alternate"
  | "not_elected"
  | "other"
  | "unknown";

export type TseVoteStudyFilters = Readonly<{
  electionYear: number | null;
  allYears: boolean;
  office: string | null;
  turn: number | null;
  outcome: TseVoteOutcome | null;
  query: string | null;
}>;

export type TseVoteGroup = Readonly<{
  year: number;
  office: string;
  turn: number;
  candidates: number;
  votes: number;
}>;

export type TseVoteStudy = Readonly<{
  votes: readonly TseVote[];
  totalCount: number;
  catalogCount: number;
  electedCount: number;
  votesTotal: number | null;
  groups: readonly TseVoteGroup[];
  availableYears: readonly number[];
  availableOffices: readonly string[];
  availableTurns: readonly number[];
  effectiveYear: number | null;
  page: number;
  pageSize: number;
  methodologyVersion: "tse-votes-study/1.0.0";
}>;

export type TseVoteStudyResult =
  | Readonly<{ state: "available"; study: TseVoteStudy }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function safeInteger(value: unknown, minimum = 0): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && /^\d+$/.test(value)
        ? Number(value)
        : Number.NaN;
  return Number.isSafeInteger(parsed) && parsed >= minimum ? parsed : null;
}

function parseVote(row: Record<string, unknown>): TseVote | null {
  const electionYear = safeInteger(row.election_year, 1900);
  const turnNumber = safeInteger(row.turn_number, 1);
  const candidateId = optionalString(row.candidate_id);
  const votesInBarreiras = safeInteger(row.votes_in_barreiras);
  const zones = safeInteger(row.zones, 1);
  const collectedAt = optionalString(row.collected_at);
  if (
    electionYear === null ||
    electionYear > 2100 ||
    turnNumber === null ||
    candidateId === null ||
    votesInBarreiras === null ||
    zones === null ||
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

function parseGroup(value: unknown): TseVoteGroup | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const year = safeInteger(row.year, 1900);
  const office = optionalString(row.office);
  const turn = safeInteger(row.turn, 1);
  const candidates = safeInteger(row.candidates, 1);
  const votes = safeInteger(row.votes);
  return year !== null && year <= 2100 && office && turn !== null &&
    candidates !== null && votes !== null
    ? { year, office, turn, candidates, votes }
    : null;
}

function integerArray(value: unknown, minimum: number): number[] | null {
  if (!Array.isArray(value)) return null;
  const parsed = value.map((item) => safeInteger(item, minimum));
  return parsed.every((item): item is number => item !== null) ? parsed : null;
}

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const parsed = value.map(optionalString);
  return parsed.every((item): item is string => item !== null) ? parsed : null;
}

function publicConfig(): { url: string; key: string } | null {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url?.startsWith("https://") || !key?.startsWith("sb_publishable_")) {
    return null;
  }
  return { url, key };
}

export async function getTseBarreirasVotesStudy(
  page = 1,
  pageSize = 50,
  filters: TseVoteStudyFilters,
): Promise<TseVoteStudyResult> {
  const config = publicConfig();
  if (
    !config ||
    !Number.isSafeInteger(page) ||
    page < 1 ||
    page > 1000 ||
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > 50
  ) {
    return { state: "unavailable" };
  }

  try {
    const payload = await fetchPublicRpcRows(
      {
        url: `${config.url}/rest/v1/rpc/get_tse_barreiras_votes_study`,
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: config.key,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          page_size: pageSize,
          page_offset: (page - 1) * pageSize,
          election_year_filter: filters.electionYear,
          use_latest_year: !filters.allYears && filters.electionYear === null,
          office_filter: filters.office,
          turn_filter: filters.turn,
          outcome_filter: filters.outcome,
          query_filter: filters.query,
        }),
      },
      { timeoutMs: 10_000, revalidateSeconds: 900 },
    );
    if (payload === null || payload.length !== 1) {
      return { state: "unavailable" };
    }

    const row = payload[0] as Record<string, unknown>;
    const rawItems = Array.isArray(row.items) ? row.items : null;
    const rawGroups = Array.isArray(row.groups) ? row.groups : null;
    const totalCount = safeInteger(row.total_count);
    const catalogCount = safeInteger(row.catalog_count);
    const electedCount = safeInteger(row.elected_count);
    const votesTotal = row.votes_total === null
      ? null
      : safeInteger(row.votes_total);
    const availableYears = integerArray(row.available_years, 1900);
    const availableOffices = stringArray(row.available_offices);
    const availableTurns = integerArray(row.available_turns, 1);
    const effectiveYear = row.effective_year === null
      ? null
      : safeInteger(row.effective_year, 1900);
    if (
      rawItems === null ||
      rawGroups === null ||
      totalCount === null ||
      catalogCount === null ||
      electedCount === null ||
      (votesTotal === null && row.votes_total !== null) ||
      availableYears === null ||
      availableOffices === null ||
      availableTurns === null ||
      (effectiveYear !== null && effectiveYear > 2100) ||
      row.methodology_version !== "tse-votes-study/1.0.0"
    ) {
      return { state: "unavailable" };
    }

    const votes = rawItems.map((item) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? parseVote(item as Record<string, unknown>)
        : null,
    );
    const groups = rawGroups.map(parseGroup);
    if (
      votes.some((vote) => vote === null) ||
      groups.some((group) => group === null) ||
      votes.length > pageSize ||
      votes.length > totalCount ||
      totalCount > catalogCount ||
      electedCount > totalCount ||
      (filters.turn === null && votesTotal !== null)
    ) {
      return { state: "unavailable" };
    }

    return {
      state: "available",
      study: {
        votes: votes as TseVote[],
        totalCount,
        catalogCount,
        electedCount,
        votesTotal,
        groups: groups as TseVoteGroup[],
        availableYears,
        availableOffices,
        availableTurns,
        effectiveYear,
        page,
        pageSize,
        methodologyVersion: "tse-votes-study/1.0.0",
      },
    };
  } catch {
    return { state: "unavailable" };
  }
}
