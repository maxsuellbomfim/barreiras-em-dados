export type DigestItem = Readonly<{
  tipo: string;
  titulo: string;
  resumo: string;
  trecho: string;
}>;

export type EditionDigest = Readonly<{
  digestId: string;
  edition: number;
  editionYear: number;
  items: readonly DigestItem[];
  partial: boolean;
  gazetteUrl: string | null;
  artifactSha256: string;
  publishedAt: string;
  reviewMode: "human" | "automated";
  methodologyVersion: string;
}>;

export type EditionDigestsResult =
  | Readonly<{ state: "available"; digests: readonly EditionDigest[] }>
  | Readonly<{ state: "unavailable" }>;

const SHA256 = /^[0-9a-f]{64}$/;
const ITEM_TYPES = new Set([
  "nomeacao",
  "exoneracao",
  "contrato",
  "licitacao",
  "decreto",
  "portaria",
  "aviso",
  "outro",
]);

function parseItems(value: unknown): readonly DigestItem[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const items: DigestItem[] = [];
  for (const raw of value) {
    if (typeof raw !== "object" || raw === null) {
      return null;
    }
    const item = raw as Record<string, unknown>;
    if (
      typeof item.tipo !== "string" ||
      !ITEM_TYPES.has(item.tipo) ||
      typeof item.titulo !== "string" ||
      item.titulo.trim().length === 0 ||
      typeof item.resumo !== "string" ||
      item.resumo.trim().length === 0 ||
      typeof item.trecho !== "string" ||
      item.trecho.trim().length === 0
    ) {
      return null;
    }
    items.push({
      tipo: item.tipo,
      titulo: item.titulo,
      resumo: item.resumo,
      trecho: item.trecho,
    });
  }
  return items;
}

function parseDigest(row: Record<string, unknown>): EditionDigest | null {
  const digestId = row.digest_id;
  const edition = row.edition;
  const editionYear = row.edition_year;
  const publishedAt = row.published_at;
  const artifactSha256 = row.artifact_sha256;
  const reviewMode = row.review_mode;
  const gazetteUrl =
    typeof row.gazette_url === "string" &&
    row.gazette_url.startsWith("https://")
      ? row.gazette_url
      : null;
  const items = parseItems(row.items);
  const stats =
    typeof row.stats === "object" && row.stats !== null
      ? (row.stats as Record<string, unknown>)
      : {};
  if (
    typeof digestId !== "string" ||
    !Number.isSafeInteger(edition) ||
    !Number.isSafeInteger(editionYear) ||
    typeof publishedAt !== "string" ||
    Number.isNaN(Date.parse(publishedAt)) ||
    typeof artifactSha256 !== "string" ||
    !SHA256.test(artifactSha256) ||
    (reviewMode !== "human" && reviewMode !== "automated") ||
    items === null ||
    items.length === 0 ||
    row.methodology_version !== "edition-digests/1.0.0"
  ) {
    return null;
  }
  return {
    digestId,
    edition: Number(edition),
    editionYear: Number(editionYear),
    items,
    partial: stats.partial === true,
    gazetteUrl,
    artifactSha256,
    publishedAt,
    reviewMode,
    methodologyVersion: "edition-digests/1.0.0",
  };
}

export async function getEditionDigests(): Promise<EditionDigestsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_edition_digests`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 40 }),
        next: { revalidate: 300 },
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
    const digests: EditionDigest[] = [];
    for (const row of payload) {
      const digest = parseDigest(row as Record<string, unknown>);
      if (digest === null) {
        return { state: "unavailable" };
      }
      digests.push(digest);
    }
    return { state: "available", digests };
  } catch {
    return { state: "unavailable" };
  }
}
