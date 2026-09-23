export type SitemapEntry = Readonly<{
  kind: "diario_edicao" | "contratacao" | "fornecedor";
  key: string;
  lastModified: string;
}>;

const KEY_PATTERNS: Record<SitemapEntry["kind"], RegExp> = {
  diario_edicao: /^\d{4}\/\d{1,6}$/,
  contratacao: /^\d{14}-\d-\d{6}\/\d{4}$/,
  // Só pessoa jurídica: um CPF (11 dígitos) nunca vira URL pública.
  fornecedor: /^\d{14}$/,
};

export function parseSitemapEntries(payload: unknown): readonly SitemapEntry[] {
  if (!Array.isArray(payload)) return [];
  const entries: SitemapEntry[] = [];
  for (const row of payload) {
    if (typeof row !== "object" || row === null) continue;
    const { entry_kind: kind, entry_key: key, last_modified: lastModified } =
      row as Record<string, unknown>;
    if (
      typeof kind === "string" &&
      kind in KEY_PATTERNS &&
      typeof key === "string" &&
      KEY_PATTERNS[kind as SitemapEntry["kind"]].test(key) &&
      typeof lastModified === "string" &&
      Number.isFinite(Date.parse(lastModified))
    ) {
      entries.push({ kind: kind as SitemapEntry["kind"], key, lastModified });
    }
  }
  return entries;
}

export async function getPublicSitemapEntries(): Promise<readonly SitemapEntry[]> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return [];
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_sitemap_entries`,
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
        next: { revalidate: 3600 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return [];
    return parseSitemapEntries(await response.json());
  } catch {
    return [];
  }
}
