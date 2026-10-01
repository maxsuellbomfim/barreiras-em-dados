// Aluguéis de imóveis por locador e contrato (municipal-property-rentals/1.3.0).
// Valores chegam como decimal em texto e continuam texto: nenhuma conta aqui.
// 1.3.0 acrescenta endereço e uso como trechos literais do histórico.
const METHODOLOGIES = new Set([
  "municipal-property-rentals/1.2.0",
  "municipal-property-rentals/1.3.0",
]);
const DECIMAL = /^-?\d+\.\d{2}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const KEY = /^O-\d+$/;

export const FIRST_RENTAL_YEAR = 2024;

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function decimal(value) {
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function isoDate(value) {
  return typeof value === "string" && ISO_DATE.test(value) ? value : null;
}

/** Linhas inválidas derrubam o conjunto: número pela metade não é publicado. */
export function parsePropertyRentalRows(rows) {
  if (!Array.isArray(rows)) return null;
  const rentals = [];
  let summary = null;
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const rental = {
      landlordName: text(row.landlord_name),
      publicBody: text(row.public_body),
      contractText: row.contract_text === null ? null : text(row.contract_text),
      commitments: count(row.commitments),
      committedAmount: decimal(row.committed_amount),
      paidAmount: decimal(row.paid_amount),
      firstCommitmentDate: isoDate(row.first_commitment_date),
      lastCommitmentDate: isoDate(row.last_commitment_date),
      description: text(row.description),
      addressText: row.address_text == null ? null : text(row.address_text),
      useText: row.use_text == null ? null : text(row.use_text),
      latestCommitmentKey: text(row.latest_commitment_key),
      gridArtifactSha256: text(row.grid_artifact_sha256),
      sourcePageUrl: text(row.source_page_url),
    };
    if (
      rental.landlordName === null ||
      rental.publicBody === null ||
      (row.contract_text !== null && rental.contractText === null) ||
      !rental.commitments ||
      rental.committedAmount === null ||
      rental.paidAmount === null ||
      rental.firstCommitmentDate === null ||
      rental.lastCommitmentDate === null ||
      rental.latestCommitmentKey === null ||
      !KEY.test(rental.latestCommitmentKey) ||
      rental.gridArtifactSha256 === null ||
      !SHA256.test(rental.gridArtifactSha256) ||
      rental.sourcePageUrl === null ||
      !rental.sourcePageUrl.startsWith("https://") ||
      !METHODOLOGIES.has(row.methodology_version)
    ) {
      return null;
    }
    const rowSummary = {
      landlords: count(row.year_landlords),
      commitments: count(row.year_commitments),
      committedAmount: decimal(row.year_committed_amount),
      paidAmount: decimal(row.year_paid_amount),
      gridMonths: count(row.year_grid_months),
    };
    const addresses = row.year_addresses == null ? null : count(row.year_addresses);
    if (Object.values(rowSummary).some((value) => value === null)) return null;
    if (row.year_addresses != null && addresses === null) return null;
    summary ??= { ...rowSummary, addresses };
    rentals.push(rental);
  }
  return { summary, rentals };
}

export function rentalYear(value, currentYear) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isSafeInteger(parsed) && parsed >= FIRST_RENTAL_YEAR && parsed <= currentYear
    ? parsed
    : currentYear;
}

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

export async function getPublicPropertyRentals(year) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_property_rentals`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ p_year: year }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const parsed = parsePropertyRentalRows(await response.json());
    return parsed ? { state: "available", ...parsed } : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
