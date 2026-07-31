export type QueridoDiarioCollectionStatus = Readonly<{
  sourceSlug: "querido-diario";
  sourceName: string;
  endpointSlug: "gazettes-api";
  latestStatus: "succeeded";
  lastSuccessfulAt: string;
  coverageStart: string;
  coverageEnd: string;
  preservedResponseCount: number;
  preservedEditionCount: number;
  collectorVersion: string;
  methodologyVersion: string;
}>;

export type CollectionStatusResult =
  | Readonly<{
      state: "available";
      data: QueridoDiarioCollectionStatus;
    }>
  | Readonly<{
      state: "unavailable";
    }>;

type StatusPayload = Readonly<{
  source_slug?: unknown;
  source_name?: unknown;
  endpoint_slug?: unknown;
  latest_status?: unknown;
  last_successful_at?: unknown;
  coverage_start?: unknown;
  coverage_end?: unknown;
  preserved_response_count?: unknown;
  preserved_edition_count?: unknown;
  collector_version?: unknown;
  methodology_version?: unknown;
}>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function parseStatusPayload(
  payload: unknown,
): QueridoDiarioCollectionStatus | null {
  if (!Array.isArray(payload) || payload.length !== 1) {
    return null;
  }

  const row = payload[0] as StatusPayload;
  if (
    row.source_slug !== "querido-diario" ||
    typeof row.source_name !== "string" ||
    row.source_name.trim().length === 0 ||
    row.endpoint_slug !== "gazettes-api" ||
    row.latest_status !== "succeeded" ||
    typeof row.last_successful_at !== "string" ||
    Number.isNaN(Date.parse(row.last_successful_at)) ||
    typeof row.coverage_start !== "string" ||
    !ISO_DATE.test(row.coverage_start) ||
    typeof row.coverage_end !== "string" ||
    !ISO_DATE.test(row.coverage_end) ||
    !isNonNegativeInteger(row.preserved_response_count) ||
    !isNonNegativeInteger(row.preserved_edition_count) ||
    typeof row.collector_version !== "string" ||
    row.collector_version.trim().length === 0 ||
    typeof row.methodology_version !== "string" ||
    row.methodology_version !==
      "querido-diario-collection-status/1.0.0"
  ) {
    return null;
  }

  return {
    sourceSlug: row.source_slug,
    sourceName: row.source_name,
    endpointSlug: row.endpoint_slug,
    latestStatus: row.latest_status,
    lastSuccessfulAt: row.last_successful_at,
    coverageStart: row.coverage_start,
    coverageEnd: row.coverage_end,
    preservedResponseCount: row.preserved_response_count,
    preservedEditionCount: row.preserved_edition_count,
    collectorVersion: row.collector_version,
    methodologyVersion: row.methodology_version,
  };
}

export async function getQueridoDiarioCollectionStatus(): Promise<CollectionStatusResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_querido_diario_collection_status`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: "{}",
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }

    const parsed = parseStatusPayload(await response.json());
    return parsed
      ? { state: "available", data: parsed }
      : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
