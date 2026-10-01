// Quem recebe o dinheiro da Prefeitura (municipal-payment-recipients/1.2.0).
// Valores chegam como decimal em texto e continuam texto: nenhuma conta aqui.
// 1.2.0: todos os credores com nome e pessoas físicas agregadas por natureza.
const METHODOLOGIES = new Set([
  "municipal-payment-recipients/1.1.0",
  "municipal-payment-recipients/1.2.0",
]);
const CNPJ = /^\d{14}$/;
const MONTH = /^\d{4}-\d{2}$/;
const DECIMAL = /^-?\d+\.\d{2}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export const FIRST_PAYMENT_YEAR = 2024;

/** Rótulos revisados pela análise contábil (ADR 0095). */
export const PAYMENT_GROUPS = Object.freeze({
  compras_servicos: "Compras, obras, serviços e demais despesas",
  pessoal: "Pessoal: salários, contratações temporárias, diárias e benefícios a servidores",
  tributos_encargos: "Encargos patronais e tributos (INSS, PIS/PASEP e outros)",
  divida: "Dívida (amortização, juros, correção e parcelamentos)",
  transferencias: "Transferências a entidades e consórcios",
  auxilios: "Auxílios, bolsas e premiações",
  judicial: "Sentenças judiciais, precatórios e depósitos judiciais",
  restituicoes: "Restituições, indenizações e ressarcimentos",
  nao_identificado: "Natureza não identificada na fonte",
});

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

function parseBodies(value) {
  if (!Array.isArray(value) || value.length === 0) return null;
  const bodies = [];
  for (const body of value) {
    const parsed = {
      publicBody: text(body?.public_body),
      payments: count(body?.payments),
      paidAmount: decimal(body?.paid_amount),
    };
    if (parsed.publicBody === null || !parsed.payments || parsed.paidAmount === null) return null;
    bodies.push(parsed);
  }
  return bodies;
}

/** CNPJ do cadastro da Receita (ADR 0093) quando há contrato confirmado; undefined = inválido. */
function parseRegistry(row) {
  if (row.registry_cnpj === null || row.registry_cnpj === undefined) {
    return row.registry_legal_name == null ? null : undefined;
  }
  const registry = {
    cnpj: typeof row.registry_cnpj === "string" && CNPJ.test(row.registry_cnpj)
      ? row.registry_cnpj : null,
    legalName: text(row.registry_legal_name),
    legalNature: text(row.registry_legal_nature),
    month: typeof row.registry_month === "string" && MONTH.test(row.registry_month)
      ? row.registry_month : null,
  };
  return Object.values(registry).some((value) => value === null) ? undefined : registry;
}

export function formatCnpj(cnpj) {
  return cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

/** Linhas inválidas derrubam o conjunto: número pela metade não é publicado. */
export function parsePaymentRecipientRows(rows) {
  if (!Array.isArray(rows)) return null;
  const groups = new Map();
  let summary = null;
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const label = PAYMENT_GROUPS[row.payment_group];
    if (!label || !METHODOLOGIES.has(row.methodology_version)) return null;
    // Nome nulo é o agregado de pessoas físicas e credores sem forma jurídica.
    const creditorName = row.creditor_name === null ? null : text(row.creditor_name);
    const recipient = {
      creditorName,
      creditors: count(row.creditors),
      payments: count(row.payments),
      paidAmount: decimal(row.paid_amount),
      firstPaymentDate: isoDate(row.first_payment_date),
      lastPaymentDate: isoDate(row.last_payment_date),
      mainNature: text(row.main_nature),
      gridArtifactSha256: text(row.grid_artifact_sha256),
      registry: parseRegistry(row),
    };
    if (
      (row.creditor_name !== null && creditorName === null) ||
      !recipient.creditors ||
      (creditorName !== null && recipient.creditors !== 1) ||
      !recipient.payments ||
      recipient.paidAmount === null ||
      recipient.firstPaymentDate === null ||
      recipient.lastPaymentDate === null ||
      recipient.gridArtifactSha256 === null ||
      !SHA256.test(recipient.gridArtifactSha256) ||
      recipient.registry === undefined ||
      (creditorName === null && recipient.registry !== null)
    ) {
      return null;
    }
    const group = {
      key: row.payment_group,
      label,
      payments: count(row.group_payments),
      creditors: count(row.group_creditors),
      paidAmount: decimal(row.group_paid_amount),
    };
    if (group.payments === null || group.creditors === null || group.paidAmount === null) {
      return null;
    }
    const rowSummary = {
      payments: count(row.year_payments),
      paidAmount: decimal(row.year_paid_amount),
      priorCommitmentAmount: decimal(row.year_prior_commitment_amount),
      uncollectedCommitmentAmount: decimal(row.year_uncollected_commitment_amount),
      bodies: parseBodies(row.year_bodies),
      gridMonths: count(row.year_grid_months),
      unreadableRows: count(row.year_unreadable_rows),
      excludedRows: count(row.year_excluded_rows),
      sourcePageUrl: text(row.source_page_url),
      refreshedAt: text(row.refreshed_at),
    };
    if (
      Object.values(rowSummary).some((value) => value === null) ||
      !rowSummary.sourcePageUrl.startsWith("https://") ||
      Number.isNaN(Date.parse(rowSummary.refreshedAt))
    ) {
      return null;
    }
    summary ??= rowSummary;
    if (!groups.has(group.key)) groups.set(group.key, { ...group, recipients: [], others: [] });
    const target = groups.get(group.key);
    if (creditorName === null) {
      target.others.push(recipient);
    } else {
      target.recipients.push(recipient);
    }
  }
  return { summary, groups: [...groups.values()] };
}

export function paymentYear(value, currentYear) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isSafeInteger(parsed) && parsed >= FIRST_PAYMENT_YEAR && parsed <= currentYear
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

export async function getPublicPaymentRecipients(year) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_public_payment_recipients`, {
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
    const parsed = parsePaymentRecipientRows(await response.json());
    return parsed ? { state: "available", ...parsed } : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}

function cents(value) {
  const match = /^(-?)(\d+)\.(\d{2})$/.exec(value ?? "");
  if (!match) return null;
  const amount = BigInt(match[2]) * 100n + BigInt(match[3]);
  return match[1] ? -amount : amount;
}

function fromCents(value) {
  const sign = value < 0n ? "-" : "";
  const absolute = value < 0n ? -value : value;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}

/**
 * Compara o pago nas ordens do portal com o pago declarado ao Tesouro (DCA).
 * Conta em centavos inteiros; a cobertura é truncada em uma casa decimal.
 */
export function compareWithDeclared(portalPaid, declaredPaid) {
  const portal = cents(portalPaid);
  const declared = cents(declaredPaid);
  if (portal === null || declared === null || declared <= 0n) return null;
  const tenths = (portal * 1000n) / declared;
  return {
    differenceAmount: fromCents(declared - portal),
    coveragePercent: `${tenths / 10n},${tenths % 10n}`,
  };
}
