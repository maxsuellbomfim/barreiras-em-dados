import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import {
  parseCguFederalAmendmentRankingRows,
  parseCguFederalAmendmentRows,
} from "../apps/web/lib/cgu-federal-amendments.mjs";
import {
  parseCguFederalAmendmentDocumentRankingRows,
  parseCguFederalAmendmentDocumentRows,
} from "../apps/web/lib/cgu-federal-amendment-documents.mjs";
import { parseFederalTransferSourceCoverageRows } from
  "../apps/web/lib/federal-transfer-source-coverage.mjs";

const SHA256 = /^[0-9a-f]{64}$/;
const RPCS = {
  coverage: "get_public_federal_transfer_source_coverage",
  currentTransfers: "get_public_parliamentary_transfers",
  currentSnapshot: "get_public_transferegov_current_snapshot_evidence",
  executions: "get_public_cgu_federal_amendment_executions",
  executionRanking: "get_public_cgu_federal_amendment_ranking",
  documents: "get_public_cgu_federal_amendment_documents",
  documentRanking: "get_public_cgu_federal_amendment_document_ranking",
};

function fail(message) {
  throw new Error(message);
}

function signedCents(value) {
  if (typeof value !== "string" || !/^-?\d+(?:\.\d{1,2})?$/.test(value)) {
    fail("valor monetario federal invalido");
  }
  const negative = value.startsWith("-");
  const [units, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
  return negative ? -cents : cents;
}

function decimal(value) {
  if (typeof value === "string" && /^-?\d+(?:\.\d{1,2})?$/.test(value.trim())) {
    return value.trim();
  }
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const cents = Math.round(value * 100);
  if (!Number.isSafeInteger(cents)) return null;
  const normalized = cents / 100;
  const tolerance = Number.EPSILON * Math.max(1, Math.abs(value)) * 4;
  return Math.abs(value - normalized) <= tolerance ? normalized.toFixed(2) : null;
}

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function compareBigInt(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compareText(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function verifyRankingOrder(rows, comparator, message) {
  const expected = [...rows].sort(comparator);
  if (expected.some((row, index) =>
    row.authorKind !== rows[index].authorKind ||
    row.authorKey !== rows[index].authorKey)) {
    fail(message);
  }
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

function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

export function parseFederalCollectorEvidence(contents, notBefore) {
  if (typeof contents !== "string" || Number.isNaN(Date.parse(notBefore ?? ""))) {
    fail("evidencia federal invalida");
  }
  const events = jsonEvents(contents);
  const executions = events.filter((event) =>
    event.event === "collector_cgu_federal_amendments_completed"
  );
  if (executions.length !== 1 || !safeCount(executions[0].amendments) ||
      executions[0].amendments < 1 ||
      !SHA256.test(executions[0].artifact_hash ?? "") ||
      !Number.isSafeInteger(executions[0].first_fiscal_year) ||
      !Number.isSafeInteger(executions[0].last_fiscal_year) ||
      executions[0].first_fiscal_year > executions[0].last_fiscal_year) {
    fail("evidencia federal da CGU invalida");
  }

  const documentEvents = events.filter((event) =>
    event.event === "collector_cgu_federal_amendment_documents_year_completed"
  ).map((event) => ({
    archiveYear: event.archive_year,
    documents: event.documents,
    artifactSha256: event.artifact_hash,
  }));
  if (documentEvents.length === 0 || documentEvents.some((event) =>
    !Number.isSafeInteger(event.archiveYear) || event.archiveYear < 2021 ||
    !safeCount(event.documents) || !SHA256.test(event.artifactSha256 ?? "")) ||
    new Set(documentEvents.map((event) => event.archiveYear)).size !==
      documentEvents.length) {
    fail("evidencia documental da CGU invalida");
  }

  const currentEvents = events.filter((event) =>
    event.event === "collector_transferegov_year_completed"
  ).map((event) => ({
    fiscalYear: event.fiscal_year,
    collectionStatus: event.coverage_status,
    distributionRecords: event.distribution_records,
    manifestRecords: event.manifest_records,
    snapshotFingerprint: event.snapshot_fingerprint,
  }));
  if (currentEvents.length === 0 || currentEvents.some((event) =>
    !Number.isSafeInteger(event.fiscalYear) || event.fiscalYear < 2021 ||
    !["complete", "empty"].includes(event.collectionStatus) ||
    !safeCount(event.distributionRecords) ||
    !safeCount(event.manifestRecords) ||
    !SHA256.test(event.snapshotFingerprint ?? "") ||
    event.manifestRecords < event.distributionRecords ||
    (event.collectionStatus === "empty" &&
      (event.distributionRecords !== 0 || event.manifestRecords !== 0)) ||
    (event.collectionStatus === "complete" && event.manifestRecords < 1)) ||
    new Set(currentEvents.map((event) => event.fiscalYear)).size !==
      currentEvents.length) {
    fail("evidencia atual do Transferegov invalida");
  }

  return {
    notBefore,
    cguExecution: {
      amendments: executions[0].amendments,
      artifactSha256: executions[0].artifact_hash,
      firstFiscalYear: executions[0].first_fiscal_year,
      lastFiscalYear: executions[0].last_fiscal_year,
    },
    cguDocuments: documentEvents,
    transferegovCurrent: currentEvents,
  };
}

function groupExecutionRows(rows) {
  const groups = new Map();
  for (const row of rows) {
    if (!row.authorIdentified || ![
      "person", "commission", "bench", "collective",
    ].includes(row.authorKind)) continue;
    const key = `${row.authorKind}:${row.authorKey}`;
    const group = groups.get(key) ?? {
      amendmentCount: 0,
      committedAmount: 0n,
      effectivePaidAmount: 0n,
      firstYear: row.fiscalYear,
      lastYear: row.fiscalYear,
    };
    group.amendmentCount += 1;
    group.committedAmount += signedCents(row.committedAmount);
    group.effectivePaidAmount += signedCents(row.effectivePaidAmount);
    group.firstYear = Math.min(group.firstYear, row.fiscalYear);
    group.lastYear = Math.max(group.lastYear, row.fiscalYear);
    groups.set(key, group);
  }
  return groups;
}

function verifyExecutionRanking(rows, groups, scope) {
  const expectedKinds = scope === "person"
    ? new Set(["person"])
    : new Set(["commission", "bench", "collective"]);
  const expectedKeys = new Set([...groups.keys()].filter((key) =>
    expectedKinds.has(key.split(":", 1)[0])
  ));
  if (rows.length !== expectedKeys.size) {
    fail(`quantidade de autores divergente no ranking federal ${scope}`);
  }
  const seen = new Set();
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const key = `${row.authorKind}:${row.authorKey}`;
    const group = groups.get(key);
    if (row.rankPosition !== index + 1 || !group || seen.has(key)) {
      fail(`autor divergente no ranking federal ${scope}`);
    }
    seen.add(key);
    if (row.amendmentCount !== group.amendmentCount) {
      fail(`quantidade de emendas divergente: ${row.authorKey}`);
    }
    if (signedCents(row.committedAmount) !== group.committedAmount) {
      fail(`total empenhado divergente: ${row.authorKey}`);
    }
    if (signedCents(row.effectivePaidAmount) !== group.effectivePaidAmount) {
      fail(`total pago divergente: ${row.authorKey}`);
    }
    if (row.firstYear !== group.firstYear || row.lastYear !== group.lastYear) {
      fail(`periodo divergente no ranking federal: ${row.authorKey}`);
    }
  }
  verifyRankingOrder(rows, (left, right) =>
    compareBigInt(
      signedCents(right.committedAmount),
      signedCents(left.committedAmount),
    ) || compareBigInt(
      signedCents(right.effectivePaidAmount),
      signedCents(left.effectivePaidAmount),
    ) || compareText(left.authorName, right.authorName),
  `ordem do ranking federal divergente: ${scope}`);
}

export function verifyCguExecutionProjection(rows, rankings, evidence) {
  if (!Array.isArray(rows) || !Array.isArray(rankings?.people) ||
      !Array.isArray(rankings?.collectives) ||
      rows.length !== evidence?.cguExecution?.amendments || rows.length === 0) {
    fail("quantidade de execucoes federais divergente");
  }
  if (rows.some((row) =>
    row.artifactSha256 !== evidence.cguExecution.artifactSha256)) {
    fail("hash da execucao federal divergente");
  }
  const groups = groupExecutionRows(rows);
  verifyExecutionRanking(rankings.people, groups, "person");
  verifyExecutionRanking(rankings.collectives, groups, "collective");
  return {
    executions: rows.length,
    executionAuthors: groups.size,
  };
}

function groupDocumentRows(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = `${row.authorKind}:${row.authorKey}`;
    const group = groups.get(key) ?? {
      amendments: new Set(),
      documents: new Set(),
      committedAmount: 0n,
      paidAmount: 0n,
      firstDocumentDate: row.documentDate,
      lastDocumentDate: row.documentDate,
    };
    group.amendments.add(row.amendmentCode);
    group.documents.add(row.documentCode);
    if (row.expenseStage === "commitment") {
      group.committedAmount += signedCents(row.committedAmount);
    }
    if (row.expenseStage === "payment") {
      group.paidAmount += signedCents(row.paidAmount);
    }
    group.firstDocumentDate = group.firstDocumentDate < row.documentDate
      ? group.firstDocumentDate
      : row.documentDate;
    group.lastDocumentDate = group.lastDocumentDate > row.documentDate
      ? group.lastDocumentDate
      : row.documentDate;
    groups.set(key, group);
  }
  return groups;
}

export function verifyCguDocumentProjection(rows, ranking, evidence) {
  const expectedCount = evidence?.cguDocuments?.reduce(
    (sum, event) => sum + event.documents,
    0,
  );
  if (!Array.isArray(rows) || !Array.isArray(ranking) || rows.length === 0 ||
      rows.length !== expectedCount) {
    fail("quantidade de documentos federais divergente");
  }
  const hashesByYear = new Map(evidence.cguDocuments.map((event) => [
    event.archiveYear,
    event.artifactSha256,
  ]));
  if (rows.some((row) =>
    row.artifactSha256 !== hashesByYear.get(row.archiveYear))) {
    fail("hash documental divergente");
  }
  const groups = groupDocumentRows(rows);
  if (ranking.length !== groups.size) {
    fail("quantidade de autores divergente no ranking documental");
  }
  const seen = new Set();
  for (let index = 0; index < ranking.length; index += 1) {
    const row = ranking[index];
    const key = `${row.authorKind}:${row.authorKey}`;
    const group = groups.get(key);
    if (row.rankPosition !== index + 1 || !group || seen.has(key)) {
      fail("autor divergente no ranking documental");
    }
    seen.add(key);
    if (row.amendmentCount !== group.amendments.size ||
        row.documentCount !== group.documents.size) {
      fail(`contagem divergente no ranking documental: ${row.authorKey}`);
    }
    if (signedCents(row.committedAmount) !== group.committedAmount) {
      fail(`total empenhado divergente no ranking documental: ${row.authorKey}`);
    }
    if (signedCents(row.paidAmount) !== group.paidAmount) {
      fail(`total pago divergente no ranking documental: ${row.authorKey}`);
    }
    if (row.firstDocumentDate !== group.firstDocumentDate ||
        row.lastDocumentDate !== group.lastDocumentDate) {
      fail(`periodo divergente no ranking documental: ${row.authorKey}`);
    }
  }
  verifyRankingOrder(ranking, (left, right) =>
    compareBigInt(
      signedCents(right.paidAmount),
      signedCents(left.paidAmount),
    ) || compareBigInt(
      signedCents(right.committedAmount),
      signedCents(left.committedAmount),
    ) || compareText(left.authorName, right.authorName),
  "ordem do ranking documental divergente");
  return { documents: rows.length, documentAuthors: groups.size };
}

export function parseCurrentFederalTransferRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = [];
  const seen = new Set();
  for (const row of rows) {
    if (typeof row !== "object" || row === null) return null;
    const externalTransferKey = requiredText(row.external_transfer_key);
    const proposalId = requiredText(row.proposal_id);
    const distributionId = requiredText(row.distribution_id);
    const fiscalYear = row.fiscal_year;
    const authorName = requiredText(row.author_name);
    const destinationAmount = decimal(row.destination_amount);
    const optionalAmounts = [
      row.proposal_amount,
      row.committed_amount,
      row.paid_amount,
    ];
    if (!externalTransferKey || !proposalId || !distributionId ||
        !Number.isSafeInteger(fiscalYear) || fiscalYear < 2021 ||
        !authorName || ![
          "person", "commission", "bench", "collective", "other",
        ].includes(row.author_kind) || destinationAmount === null ||
        optionalAmounts.some((value) => value !== null && decimal(value) === null) ||
        !requiredText(row.collected_at) ||
        Number.isNaN(Date.parse(row.collected_at)) ||
        !requiredText(row.source_url)?.startsWith("https://") ||
        !SHA256.test(requiredText(row.artifact_sha256) ?? "") ||
        (row.bank_order_date !== null && row.bank_order_date !== undefined &&
          !/^\d{4}-\d{2}-\d{2}$/.test(row.bank_order_date)) ||
        ![
          "exact_single_distribution", "ambiguous_multiple_distributions",
        ].includes(row.stage_attribution_status) ||
        row.methodology_version !== "parliamentary-transfers/1.0.0" ||
        seen.has(externalTransferKey)) {
      return null;
    }
    seen.add(externalTransferKey);
    parsed.push({ externalTransferKey, fiscalYear });
  }
  return parsed;
}

export function parseCurrentTransferegovSnapshotRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = [];
  const seen = new Set();
  for (const row of rows) {
    if (typeof row !== "object" || row === null ||
        !Number.isSafeInteger(row.fiscal_year) || row.fiscal_year < 2021 ||
        !["complete", "empty"].includes(row.coverage_status) ||
        !safeCount(row.record_count) ||
        (row.coverage_status === "complete" && row.record_count < 1) ||
        (row.coverage_status === "empty" && row.record_count !== 0) ||
        !SHA256.test(requiredText(row.snapshot_fingerprint) ?? "") ||
        !requiredText(row.last_attempted_at) ||
        Number.isNaN(Date.parse(row.last_attempted_at)) ||
        !requiredText(row.source_url)?.startsWith("https://") ||
        row.methodology_version !== "transferegov-current-snapshot/1.1.0" ||
        seen.has(row.fiscal_year)) {
      return null;
    }
    seen.add(row.fiscal_year);
    parsed.push({
      fiscalYear: row.fiscal_year,
      collectionStatus: row.coverage_status,
      recordCount: row.record_count,
      snapshotFingerprint: row.snapshot_fingerprint,
      lastAttemptedAt: row.last_attempted_at,
    });
  }
  return parsed;
}

export function verifyTransferegovSnapshotEvidence(rows, evidence) {
  if (!Array.isArray(rows) || !Array.isArray(evidence?.transferegovCurrent) ||
      rows.length !== evidence.transferegovCurrent.length) {
    fail("evidencia de snapshot Transferegov divergente");
  }
  const index = new Map(rows.map((row) => [row.fiscalYear, row]));
  for (const event of evidence.transferegovCurrent) {
    const row = index.get(event.fiscalYear);
    if (!row || row.collectionStatus !== event.collectionStatus ||
        row.recordCount !== event.manifestRecords) {
      fail(`contagem do snapshot Transferegov divergente: ${event.fiscalYear}`);
    }
    if (row.snapshotFingerprint !== event.snapshotFingerprint) {
      fail(
        `impressao do snapshot Transferegov divergente: ${event.fiscalYear}`,
      );
    }
    const attemptedAt = Date.parse(row.lastAttemptedAt ?? "");
    const startedAt = Date.parse(evidence.notBefore);
    if (Number.isNaN(attemptedAt) || attemptedAt < startedAt - 5 * 60 * 1000) {
      fail(`snapshot Transferegov antigo: ${event.fiscalYear}`);
    }
  }
  return { transferegovSnapshots: rows.length };
}

function countByYear(rows, field) {
  const result = new Map();
  for (const row of rows) {
    const year = row[field];
    result.set(year, (result.get(year) ?? 0) + 1);
  }
  return result;
}

function requireCoverage(index, sourceKey, fiscalYear, count, notBefore) {
  const row = index.get(`${sourceKey}:${fiscalYear}`);
  const expectedStatus = count > 0 ? "observed" : "empty";
  if (!row || row.coverageStatus !== expectedStatus || row.recordCount !== count) {
    fail(`cobertura federal divergente: ${sourceKey}:${fiscalYear}`);
  }
  const attemptedAt = Date.parse(row.lastAttemptedAt ?? "");
  const startedAt = Date.parse(notBefore);
  if (Number.isNaN(attemptedAt) || attemptedAt < startedAt - 5 * 60 * 1000) {
    fail(`projecao federal antiga: ${sourceKey}:${fiscalYear}`);
  }
}

export function verifyFederalSourceCoverage(
  coverage,
  executions,
  documents,
  currentTransfers,
  evidence,
) {
  if (!Array.isArray(coverage) || !Array.isArray(executions) ||
      !Array.isArray(documents) || !Array.isArray(currentTransfers) || !evidence) {
    fail("cobertura federal invalida");
  }
  const index = new Map();
  for (const row of coverage) {
    const key = `${row.sourceKey}:${row.fiscalYear}`;
    if (index.has(key)) fail(`cobertura federal duplicada: ${key}`);
    index.set(key, row);
  }
  const executionCounts = countByYear(executions, "fiscalYear");
  let cguExecutionYears = 0;
  for (let year = evidence.cguExecution.firstFiscalYear;
    year <= evidence.cguExecution.lastFiscalYear; year += 1) {
    requireCoverage(
      index,
      "cgu_execution",
      year,
      executionCounts.get(year) ?? 0,
      evidence.notBefore,
    );
    cguExecutionYears += 1;
  }
  const documentCounts = countByYear(documents, "archiveYear");
  for (const event of evidence.cguDocuments) {
    if ((documentCounts.get(event.archiveYear) ?? 0) !== event.documents) {
      fail(`quantidade documental divergente em ${event.archiveYear}`);
    }
    requireCoverage(
      index,
      "cgu_documents",
      event.archiveYear,
      event.documents,
      evidence.notBefore,
    );
  }
  const currentCounts = countByYear(currentTransfers, "fiscalYear");
  const currentYears = new Set(evidence.transferegovCurrent.map((event) =>
    event.fiscalYear));
  if (currentTransfers.some((row) => !currentYears.has(row.fiscalYear))) {
    fail("projecao atual do Transferegov fora da execucao comprovada");
  }
  for (const event of evidence.transferegovCurrent) {
    const publicCount = currentCounts.get(event.fiscalYear) ?? 0;
    if (event.collectionStatus === "empty" && publicCount !== 0) {
      fail(
        `coleta vazia do Transferegov manteve registros publicos: ${event.fiscalYear}`,
      );
    }
    requireCoverage(
      index,
      "transferegov_current",
      event.fiscalYear,
      publicCount,
      evidence.notBefore,
    );
  }
  return {
    cguExecutionYears,
    cguDocumentYears: evidence.cguDocuments.length,
    transferegovYears: evidence.transferegovCurrent.length,
  };
}

function rpcUrl(baseUrl, name) {
  const base = new URL(baseUrl);
  if (base.protocol !== "https:") fail("SUPABASE_URL deve usar HTTPS");
  return new URL(`/rest/v1/rpc/${name}`, base).toString();
}

function sleep(delay) {
  return new Promise((resolve) => setTimeout(resolve, delay));
}

async function waitBeforeRetry(options, attempt) {
  const delay = Math.min(1_000 * 2 ** (attempt - 1), 8_000);
  await (options.sleepImpl ?? sleep)(delay);
}

export async function fetchRpcRows(name, options, body = {}) {
  const fetchImpl = options.fetchImpl ?? fetch;
  const maxAttempts = Number.isSafeInteger(options.retryAttempts) &&
      options.retryAttempts >= 1 && options.retryAttempts <= 10
    ? options.retryAttempts
    : 7;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
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
        if (attempt < maxAttempts && (response.status === 408 ||
            response.status === 425 || response.status === 429 ||
            response.status >= 500)) {
          await waitBeforeRetry(options, attempt);
          continue;
        }
        fail(`RPC publica ${name} respondeu HTTP ${response.status}`);
      }
      const rows = await response.json();
      if (!Array.isArray(rows)) fail(`RPC publica ${name} retornou contrato invalido`);
      return rows;
    } catch (error) {
      if (error instanceof Error && error.message.startsWith("RPC publica")) {
        throw error;
      }
      if (attempt === maxAttempts) {
        fail(`RPC publica ${name} ficou indisponivel`);
      }
      await waitBeforeRetry(options, attempt);
    }
  }
  fail(`RPC publica ${name} ficou indisponivel`);
}

async function mapWithConcurrency(values, limit, callback) {
  if (!Array.isArray(values) || values.length === 0) return [];
  const results = new Array(values.length);
  let cursor = 0;
  async function worker() {
    while (cursor < values.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await callback(values[index], index);
    }
  }
  const workerCount = Math.min(limit, values.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  return results;
}

async function fetchBoundedRows(name, options, body, pageSize) {
  const rows = await fetchRpcRows(name, options, { ...body, page_size: pageSize });
  if (rows.length >= pageSize) {
    fail(`RPC publica ${name} atingiu o limite sem paginacao comprovada`);
  }
  return rows;
}

function requireParsed(rows, parser, name, ...args) {
  const parsed = parser(rows, ...args);
  if (parsed === null) fail(`RPC publica ${name} violou o contrato editorial`);
  return parsed;
}

export async function verifyPublicFederalProjection(options) {
  if (typeof options?.baseUrl !== "string" ||
      typeof options?.publishableKey !== "string" ||
      options.publishableKey.length < 20 || !options.collectorEvidence) {
    fail("configuracao do gate federal ausente");
  }
  const evidence = options.collectorEvidence;
  const executionYears = [];
  for (let year = evidence.cguExecution.firstFiscalYear;
    year <= evidence.cguExecution.lastFiscalYear; year += 1) {
    executionYears.push(year);
  }
  const [personRankingRows, collectiveRankingRows,
    documentRankingRows] = await Promise.all([
    fetchBoundedRows(RPCS.executionRanking, options, {
      author_scope: "person",
      fiscal_year_filter: null,
    }, 200),
    fetchBoundedRows(RPCS.executionRanking, options, {
      author_scope: "collective",
      fiscal_year_filter: null,
    }, 200),
    fetchBoundedRows(RPCS.documentRanking, options, {
      archive_year_filter: null,
    }, 200),
  ]);
  const executionPages = await mapWithConcurrency(
    executionYears,
    4,
    (year) => fetchBoundedRows(
      RPCS.executions,
      options,
      { fiscal_year_filter: year, author_key_filter: null },
      200,
    ),
  );
  const documentPages = await mapWithConcurrency(
    evidence.cguDocuments,
    4,
    (event) => fetchBoundedRows(
      RPCS.documents,
      options,
      { archive_year_filter: event.archiveYear, author_key_filter: null },
      500,
    ),
  );
  const currentTransferPages = await mapWithConcurrency(
    evidence.transferegovCurrent,
    4,
    (event) => fetchBoundedRows(
      RPCS.currentTransfers,
      options,
      { fiscal_year_filter: event.fiscalYear, author_kind_filter: null },
      200,
    ),
  );
  const currentSnapshotRows = await fetchRpcRows(RPCS.currentSnapshot, options);
  const coverageRows = await fetchRpcRows(RPCS.coverage, options);
  const executions = requireParsed(
    executionPages.flat(),
    parseCguFederalAmendmentRows,
    RPCS.executions,
  );
  const documents = requireParsed(
    documentPages.flat(),
    parseCguFederalAmendmentDocumentRows,
    RPCS.documents,
  );
  const currentTransfers = requireParsed(
    currentTransferPages.flat(),
    parseCurrentFederalTransferRows,
    RPCS.currentTransfers,
  );
  const executionSummary = verifyCguExecutionProjection(executions, {
    people: requireParsed(
      personRankingRows,
      parseCguFederalAmendmentRankingRows,
      RPCS.executionRanking,
      "person",
    ),
    collectives: requireParsed(
      collectiveRankingRows,
      parseCguFederalAmendmentRankingRows,
      RPCS.executionRanking,
      "collective",
    ),
  }, evidence);
  const documentSummary = verifyCguDocumentProjection(
    documents,
    requireParsed(
      documentRankingRows,
      parseCguFederalAmendmentDocumentRankingRows,
      RPCS.documentRanking,
    ),
    evidence,
  );
  const coverageSummary = verifyFederalSourceCoverage(
    requireParsed(
      coverageRows,
      parseFederalTransferSourceCoverageRows,
      RPCS.coverage,
    ),
    executions,
    documents,
    currentTransfers,
    evidence,
  );
  const snapshotSummary = verifyTransferegovSnapshotEvidence(
    requireParsed(
      currentSnapshotRows,
      parseCurrentTransferegovSnapshotRows,
      RPCS.currentSnapshot,
    ),
    evidence,
  );
  return {
    ...executionSummary,
    ...documentSummary,
    ...coverageSummary,
    ...snapshotSummary,
  };
}

function readArgument(argv, name) {
  const index = argv.indexOf(name);
  return index >= 0 ? argv[index + 1] : null;
}

async function main() {
  try {
    const argv = process.argv.slice(2);
    const collectorLogPath = readArgument(argv, "--collector-log");
    const notBeforePath = readArgument(argv, "--not-before-file");
    if (!collectorLogPath || !notBeforePath) fail("evidencia do coletor ausente");
    const [collectorLog, notBefore] = await Promise.all([
      readFile(collectorLogPath, "utf8"),
      readFile(notBeforePath, "utf8").then((value) => value.trim()),
    ]);
    const summary = await verifyPublicFederalProjection({
      baseUrl: process.env.SUPABASE_URL,
      publishableKey: process.env.SUPABASE_PUBLISHABLE_KEY,
      collectorEvidence: parseFederalCollectorEvidence(collectorLog, notBefore),
    });
    console.log(JSON.stringify({
      event: "public_projection_gate",
      scope: "federal-transfers",
      status: "passed",
      ...summary,
    }));
  } catch (error) {
    console.error(JSON.stringify({
      event: "public_projection_gate",
      scope: "federal-transfers",
      status: "failed",
      reason: error instanceof Error ? error.message : "erro desconhecido",
    }));
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
