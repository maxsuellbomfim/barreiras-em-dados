import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import { parseBahiaStateExecutionCoverageRows } from
  "../apps/web/lib/bahia-state-execution-coverage.mjs";
import {
  parseBahiaSpecialTransferAnnualCoverage,
  parseBahiaSpecialTransferPayments,
  parseBahiaSpecialTransferRanking,
} from "../apps/web/lib/bahia-special-transfers.mjs";
import { parseStateAmendmentSourceCoverageRows } from
  "../apps/web/lib/state-amendment-source-coverage.mjs";

const SCOPES = new Set(["state-execution", "special-transfers", "loa"]);
const SHA256 = /^[0-9a-f]{64}$/;
const RPCS = {
  stateExecution: "get_public_bahia_state_execution_annual_coverage",
  specialCoverage: "get_public_bahia_special_transfer_annual_coverage",
  specialPayments: "get_public_bahia_special_transfer_payments",
  specialRanking: "get_public_bahia_special_transfer_ranking",
  loaCoverage: "get_public_state_amendment_source_coverage",
};

function fail(message) {
  throw new Error(message);
}

function toCents(value) {
  if (typeof value !== "string" || !/^\d+(?:\.\d{1,2})?$/.test(value)) {
    fail("valor monetario publico invalido");
  }
  const [units, fraction = ""] = value.split(".");
  return BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
}

function sameYears(left, right) {
  if (left.size !== right.size) return false;
  return [...left].every((year) => right.has(year));
}

function requireSingleSnapshot(rows, label) {
  const hashes = new Set(rows.map((row) => row.sourceArtifactSha256));
  const collectedAt = new Set(rows.map((row) => row.sourceCollectedAt));
  if (hashes.size !== 1 || collectedAt.size !== 1 ||
      !SHA256.test([...hashes][0] ?? "") ||
      Number.isNaN(Date.parse([...collectedAt][0] ?? ""))) {
    fail(`linhagem divergente na ${label}`);
  }
  return {
    artifactSha256: [...hashes][0],
    collectedAt: [...collectedAt][0],
  };
}

export function verifyStateExecutionProjection(coverage, expected = {}) {
  if (!Array.isArray(coverage) || coverage.length === 0) {
    fail("nenhum exercicio estadual publicado");
  }
  let sourceRecords = 0;
  for (const row of coverage) {
    if (!Number.isSafeInteger(row.fiscalYear) ||
        !Number.isSafeInteger(row.sourceAggregateCount) ||
        row.sourceAggregateCount < 1) {
      fail("cobertura estadual publica invalida");
    }
    sourceRecords += row.sourceAggregateCount;
    if (!Number.isSafeInteger(sourceRecords)) {
      fail("contagem estadual excede o limite seguro");
    }
  }
  const snapshot = requireSingleSnapshot(coverage, "execucao estadual");
  if (expected.artifactSha256 &&
      snapshot.artifactSha256 !== expected.artifactSha256) {
    fail("execucao estadual nao corresponde ao arquivo recem-coletado");
  }
  return { years: coverage.length, sourceRecords };
}

export function verifyLoaProjection(
  loaCoverage,
  executionCoverage,
  expected = {},
) {
  if (!Array.isArray(loaCoverage) || loaCoverage.length === 0) {
    fail("nenhum exercicio da LOA publicado");
  }
  verifyStateExecutionProjection(executionCoverage);
  const loaYears = new Set(loaCoverage.map((row) => row.fiscalYear));
  const executionYears = new Set(
    executionCoverage.map((row) => row.fiscalYear),
  );
  if (!sameYears(loaYears, executionYears)) {
    fail("exercicios divergentes entre LOA e execucao estadual");
  }
  if (expected.years) {
    const expectedYears = new Map(expected.years.map((row) => [
      row.fiscalYear,
      row.collectionStatus,
    ]));
    if (!sameYears(loaYears, new Set(expectedYears.keys()))) {
      fail("exercicios divergentes entre coleta e projecao da LOA");
    }
    const notBefore = Date.parse(expected.notBefore ?? "");
    if (Number.isNaN(notBefore)) fail("inicio da coleta da LOA invalido");
    const clockToleranceMs = 5 * 60 * 1000;
    for (const row of loaCoverage) {
      const collectionStatus = expectedYears.get(row.fiscalYear);
      const compatibleStatus = collectionStatus === "complete"
        ? ["observed", "empty"].includes(row.loaStatus)
        : collectionStatus === "blocked" && row.loaStatus === "blocked";
      if (!compatibleStatus) {
        fail(`estado da LOA divergente em ${row.fiscalYear}`);
      }
      const attemptedAt = Date.parse(row.lastAttemptedAt ?? "");
      if (Number.isNaN(attemptedAt) ||
          attemptedAt < notBefore - clockToleranceMs) {
        fail(`projecao antiga da LOA em ${row.fiscalYear}`);
      }
    }
  }
  return {
    years: loaCoverage.length,
    observedYears: loaCoverage.filter((row) => row.loaStatus === "observed")
      .length,
    blockedYears: loaCoverage.filter((row) => row.loaStatus === "blocked")
      .length,
  };
}

function paymentsByYear(payments) {
  const result = new Map();
  for (const payment of payments) {
    result.set(payment.fiscalYear, (result.get(payment.fiscalYear) ?? 0) + 1);
  }
  return result;
}

function linkedPaymentsByAuthor(payments) {
  const result = new Map();
  for (const payment of payments) {
    if (payment.associationStatus !==
        "approved_official_author_code_crosswalk") continue;
    const current = result.get(payment.authorKey) ?? [];
    current.push(payment);
    result.set(payment.authorKey, current);
  }
  return result;
}

function verifyRankingRow(row, authorPayments) {
  if (row.paymentCount !== authorPayments.length) {
    fail(`quantidade de pagamentos divergente no ranking: ${row.authorKey}`);
  }
  const amendments = new Set(
    authorPayments.map((payment) => payment.officialAmendmentCode),
  );
  if (row.amendmentCount !== amendments.size) {
    fail(`quantidade de emendas divergente no ranking: ${row.authorKey}`);
  }
  const paidCents = authorPayments.reduce(
    (sum, payment) => sum + toCents(payment.paymentAmount),
    0n,
  );
  if (toCents(row.paidAmount) !== paidCents) {
    fail(`total pago divergente no ranking: ${row.authorKey}`);
  }
  const dates = authorPayments.map((payment) => payment.paymentDate).sort();
  if (row.firstPaymentDate !== dates[0] ||
      row.lastPaymentDate !== dates.at(-1)) {
    fail(`periodo de pagamentos divergente no ranking: ${row.authorKey}`);
  }
}

export function verifySpecialTransferProjection({
  coverage,
  payments,
  ranking,
}, expected = {}) {
  if (!Array.isArray(coverage) || coverage.length === 0 ||
      !Array.isArray(payments) || !Array.isArray(ranking)) {
    fail("contrato publico de transferencias especiais invalido");
  }
  const observedByYear = paymentsByYear(payments);
  const coveredYears = new Set();
  let territorialPayments = 0;
  for (const row of coverage) {
    coveredYears.add(row.fiscalYear);
    territorialPayments += row.territorialPaymentCount;
    if ((observedByYear.get(row.fiscalYear) ?? 0) !==
        row.territorialPaymentCount) {
      fail(`contagem territorial divergente em ${row.fiscalYear}`);
    }
  }
  if (territorialPayments === 0 || payments.length === 0) {
    fail("nenhum pagamento territorial publicado");
  }
  if (territorialPayments !== payments.length ||
      [...observedByYear.keys()].some((year) => !coveredYears.has(year))) {
    fail("pagamentos territoriais fora da cobertura anual");
  }
  const coverageSnapshot = requireSingleSnapshot(
    coverage,
    "cobertura das transferencias especiais",
  );
  const paymentSnapshot = requireSingleSnapshot(
    payments,
    "projecao dos pagamentos especiais",
  );
  if (coverageSnapshot.artifactSha256 !== paymentSnapshot.artifactSha256 ||
      coverageSnapshot.collectedAt !== paymentSnapshot.collectedAt) {
    fail("linhagem divergente entre cobertura e pagamentos especiais");
  }
  if (expected.artifactSha256 &&
      coverageSnapshot.artifactSha256 !== expected.artifactSha256) {
    fail("pagamentos especiais nao correspondem ao arquivo recem-coletado");
  }

  const linkedByAuthor = linkedPaymentsByAuthor(payments);
  if (ranking.length !== linkedByAuthor.size) {
    fail("quantidade de autores divergente no ranking");
  }
  for (let index = 0; index < ranking.length; index += 1) {
    const row = ranking[index];
    if (row.rankPosition !== index + 1) {
      fail("posicoes do ranking nao sao continuas");
    }
    const authorPayments = linkedByAuthor.get(row.authorKey);
    if (!authorPayments) {
      fail(`autor sem pagamentos reconciliados: ${row.authorKey}`);
    }
    verifyRankingRow(row, authorPayments);
    linkedByAuthor.delete(row.authorKey);
  }
  if (linkedByAuthor.size !== 0) {
    fail("pagamentos vinculados ausentes do ranking");
  }
  return {
    years: coverage.length,
    territorialPayments,
    rankedAuthors: ranking.length,
    unlinkedPayments: payments.filter((payment) =>
      payment.associationStatus === "not_linked"
    ).length,
  };
}

function rpcUrl(baseUrl, name) {
  const base = new URL(baseUrl);
  if (base.protocol !== "https:") fail("SUPABASE_URL deve usar HTTPS");
  return new URL(`/rest/v1/rpc/${name}`, base).toString();
}

async function fetchRpcRows(name, options, body = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      const response = await fetchImpl(rpcUrl(options.baseUrl, name), {
        method: "POST",
        headers: {
          apikey: options.publishableKey,
          authorization: `Bearer ${options.publishableKey}`,
          accept: "application/json",
          "accept-profile": "api",
          "content-profile": "api",
          "content-type": "application/json",
        },
        body: JSON.stringify(body),
        cache: "no-store",
        signal: AbortSignal.timeout(options.timeoutMs ?? 10_000),
      });
      if (!response.ok) {
        if (attempt === 1 && (response.status === 408 ||
            response.status === 425 || response.status === 429 ||
            response.status >= 500)) continue;
        fail(`RPC publica ${name} respondeu HTTP ${response.status}`);
      }
      const rows = await response.json();
      if (!Array.isArray(rows)) fail(`RPC publica ${name} retornou contrato invalido`);
      return rows;
    } catch (error) {
      if (error instanceof Error && error.message.startsWith("RPC publica")) {
        throw error;
      }
      if (attempt === 2) fail(`RPC publica ${name} ficou indisponivel`);
    }
  }
  fail(`RPC publica ${name} ficou indisponivel`);
}

export async function fetchAllRpcRows(name, options, pagination) {
  const pageSize = pagination?.pageSize;
  const body = pagination?.body ?? {};
  if (!Number.isSafeInteger(pageSize) || pageSize < 1) {
    fail(`tamanho de pagina invalido para ${name}`);
  }
  const rows = [];
  for (let pageOffset = 0; pageOffset <= 1_000_000;
    pageOffset += pageSize) {
    const page = await fetchRpcRows(name, options, {
      ...body,
      page_offset: pageOffset,
      page_size: pageSize,
    });
    if (page.length > pageSize) {
      fail(`RPC publica ${name} excedeu o tamanho da pagina`);
    }
    rows.push(...page);
    if (page.length < pageSize) return rows;
  }
  fail(`RPC publica ${name} excedeu o limite seguro de paginacao`);
}

function requireParsed(rows, parser, name) {
  const parsed = parser(rows);
  if (parsed === null) fail(`RPC publica ${name} violou o contrato editorial`);
  return parsed;
}

export async function verifyPublicProjection(scope, options) {
  if (!SCOPES.has(scope)) fail(`escopo desconhecido: ${scope}`);
  if (typeof options?.baseUrl !== "string" ||
      typeof options?.publishableKey !== "string" ||
      options.publishableKey.length < 20) {
    fail("credenciais publicas do Supabase ausentes");
  }
  if (!options.collectorEvidence) fail("evidencia do coletor ausente");
  if (scope === "state-execution") {
    const rows = await fetchRpcRows(RPCS.stateExecution, options);
    return verifyStateExecutionProjection(
      requireParsed(
        rows,
        parseBahiaStateExecutionCoverageRows,
        RPCS.stateExecution,
      ),
      options.collectorEvidence,
    );
  }
  if (scope === "loa") {
    const [loaRows, executionRows] = await Promise.all([
      fetchRpcRows(RPCS.loaCoverage, options),
      fetchRpcRows(RPCS.stateExecution, options),
    ]);
    return verifyLoaProjection(
      requireParsed(
        loaRows,
        parseStateAmendmentSourceCoverageRows,
        RPCS.loaCoverage,
      ),
      requireParsed(
        executionRows,
        parseBahiaStateExecutionCoverageRows,
        RPCS.stateExecution,
      ),
      options.collectorEvidence,
    );
  }
  const [coverageRows, paymentRows, rankingRows] = await Promise.all([
    fetchRpcRows(RPCS.specialCoverage, options),
    fetchAllRpcRows(RPCS.specialPayments, options, {
      pageSize: 200,
      body: {
        fiscal_year_filter: null,
        author_key_filter: null,
      },
    }),
    fetchAllRpcRows(RPCS.specialRanking, options, {
      pageSize: 50,
      body: { fiscal_year_filter: null },
    }),
  ]);
  return verifySpecialTransferProjection({
    coverage: requireParsed(
      coverageRows,
      parseBahiaSpecialTransferAnnualCoverage,
      RPCS.specialCoverage,
    ),
    payments: requireParsed(
      paymentRows,
      parseBahiaSpecialTransferPayments,
      RPCS.specialPayments,
    ),
    ranking: requireParsed(
      rankingRows,
      parseBahiaSpecialTransferRanking,
      RPCS.specialRanking,
    ),
  }, options.collectorEvidence);
}

function readArgument(argv, name) {
  const index = argv.indexOf(name);
  return index >= 0 ? argv[index + 1] : null;
}

function jsonEvents(contents) {
  return contents.split(/\r?\n/).flatMap((line) => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("{")) return [];
    try {
      const parsed = JSON.parse(trimmed);
      return typeof parsed === "object" && parsed !== null ? [parsed] : [];
    } catch {
      return [];
    }
  });
}

export function parseCollectorEvidence(scope, contents, notBefore = null) {
  if (!SCOPES.has(scope) || typeof contents !== "string") {
    fail("evidencia do coletor invalida");
  }
  const events = jsonEvents(contents);
  if (scope === "loa") {
    const completed = events.filter((event) =>
      event.event === "collector_bahia_state_loa_year_completed"
    );
    const years = completed.map((event) => ({
      fiscalYear: event.fiscal_year,
      collectionStatus: event.coverage_status,
    }));
    if (years.length === 0 ||
        years.some((row) => !Number.isSafeInteger(row.fiscalYear) ||
          !["complete", "blocked"].includes(row.collectionStatus)) ||
        new Set(years.map((row) => row.fiscalYear)).size !== years.length ||
        Number.isNaN(Date.parse(notBefore ?? ""))) {
      fail("evidencia anual do coletor da LOA invalida");
    }
    return { years, notBefore };
  }
  const eventName = scope === "state-execution"
    ? "collector_bahia_state_amendments_completed"
    : "collector_bahia_special_transfers_completed";
  const completed = events.filter((event) => event.event === eventName);
  if (completed.length !== 1 ||
      !SHA256.test(completed[0].artifact_hash ?? "")) {
    fail("hash do arquivo recem-coletado ausente");
  }
  return { artifactSha256: completed[0].artifact_hash };
}

async function main() {
  const argv = process.argv.slice(2);
  const scope = readArgument(argv, "--scope");
  try {
    const collectorLogPath = readArgument(argv, "--collector-log");
    if (!collectorLogPath) fail("log do coletor ausente");
    const collectorLog = await readFile(collectorLogPath, "utf8");
    const notBeforePath = readArgument(argv, "--not-before-file");
    const notBefore = notBeforePath
      ? (await readFile(notBeforePath, "utf8")).trim()
      : null;
    const summary = await verifyPublicProjection(scope, {
      baseUrl: process.env.SUPABASE_URL,
      publishableKey: process.env.SUPABASE_PUBLISHABLE_KEY,
      collectorEvidence: parseCollectorEvidence(scope, collectorLog, notBefore),
    });
    console.log(JSON.stringify({
      event: "public_projection_gate",
      scope,
      status: "passed",
      ...summary,
    }));
  } catch (error) {
    console.error(JSON.stringify({
      event: "public_projection_gate",
      scope,
      status: "failed",
      reason: error instanceof Error ? error.message : "erro desconhecido",
    }));
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
