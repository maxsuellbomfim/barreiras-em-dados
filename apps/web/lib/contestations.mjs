// Contestação anônima com protocolo (ADR 0099). O banco valida de novo; aqui
// só normaliza a entrada e traduz a resposta. Texto e contato nunca voltam.
const PROTOCOL = /^C-[0-9A-F]{10}$/;
const STATUSES = new Set(["received", "under_review", "upheld", "rejected", "withdrawn"]);
const SITE_HOSTS = new Set(["barreiras-em-dados.vercel.app", "localhost"]);

/** Aceita caminho ("/indicios") ou endereço completo do próprio site. */
export function normalizeTargetPath(value) {
  const input = typeof value === "string" ? value.trim() : "";
  if (!input) return null;
  if (input.startsWith("/")) {
    return /^\/\S*$/.test(input) && input.length <= 300 ? input : null;
  }
  try {
    const url = new URL(input);
    if (!SITE_HOSTS.has(url.hostname)) return null;
    const path = `${url.pathname}${url.search}`;
    return path.length <= 300 ? path : null;
  } catch {
    return null;
  }
}

export function normalizeProtocol(value) {
  const protocol = typeof value === "string" ? value.trim().toUpperCase() : "";
  return PROTOCOL.test(protocol) ? protocol : null;
}

export const STATUS_LABELS = {
  received: "Recebida — aguardando nova conferência",
  under_review: "Em nova conferência",
  upheld: "Procedente — o conteúdo foi corrigido ou retirado",
  rejected: "Não procedente — a evidência original se sustenta",
  withdrawn: "Retirada",
};

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

function rpc(config, name, body, { cache } = {}) {
  return fetch(`${config.url}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: config.key,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache,
    signal: AbortSignal.timeout(8_000),
  });
}

export async function submitContestation({ targetPath, description, evidenceUrl, contact }) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await rpc(config, "submit_public_contestation", {
      p_target_path: targetPath,
      p_description: description,
      p_evidence_url: evidenceUrl || null,
      p_contact: contact || null,
    }, { cache: "no-store" });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      // Mensagens de validação do banco são escritas para o público.
      const message = typeof payload?.message === "string" ? payload.message : null;
      return response.status === 400 && message
        ? { state: "invalid", message }
        : { state: "unavailable" };
    }
    const protocol = normalizeProtocol(Array.isArray(payload) ? payload[0]?.protocol : null);
    return protocol ? { state: "created", protocol } : { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}

export function parseContestationRows(rows) {
  if (!Array.isArray(rows)) return null;
  if (rows.length === 0) return { state: "not_found" };
  const row = rows[0];
  const protocol = normalizeProtocol(row?.protocol);
  if (
    rows.length !== 1 ||
    protocol === null ||
    typeof row.target_path !== "string" ||
    !row.target_path.startsWith("/") ||
    !STATUSES.has(row.status) ||
    typeof row.created_at !== "string" ||
    (row.resolution_note !== null && typeof row.resolution_note !== "string") ||
    (row.resolved_at !== null && typeof row.resolved_at !== "string")
  ) {
    return null;
  }
  return {
    state: "found",
    protocol,
    targetPath: row.target_path,
    status: row.status,
    resolutionNote: row.resolution_note,
    createdAt: row.created_at,
    resolvedAt: row.resolved_at,
  };
}

export async function getContestation(protocol) {
  const config = publicDataConfig();
  if (!config) return { state: "unavailable" };
  try {
    const response = await rpc(config, "get_public_contestation", { p_protocol: protocol }, {
      cache: "no-store",
    });
    if (!response.ok) return { state: "unavailable" };
    return parseContestationRows(await response.json()) ?? { state: "unavailable" };
  } catch {
    return { state: "unavailable" };
  }
}
