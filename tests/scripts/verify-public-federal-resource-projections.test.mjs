import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchRpcRows,
  parseCurrentFederalTransferRows,
  parseFederalCollectorEvidence,
  verifyCguDocumentProjection,
  verifyCguExecutionProjection,
  verifyFederalSourceCoverage,
} from "../../scripts/verify-public-federal-resource-projections.mjs";

const notBefore = "2026-09-04T02:00:00Z";
const collectedAt = "2026-09-04T02:01:00Z";
const aggregateHash = "a".repeat(64);
const document2022Hash = "b".repeat(64);
const document2023Hash = "c".repeat(64);

const collectorLog = [
  JSON.stringify({
    event: "collector_cgu_federal_amendments_completed",
    amendments: 2,
    artifact_hash: aggregateHash,
    first_fiscal_year: 2022,
    last_fiscal_year: 2023,
  }),
  JSON.stringify({
    event: "collector_cgu_federal_amendment_documents_year_completed",
    archive_year: 2022,
    documents: 2,
    artifact_hash: document2022Hash,
  }),
  JSON.stringify({
    event: "collector_cgu_federal_amendment_documents_year_completed",
    archive_year: 2023,
    documents: 1,
    artifact_hash: document2023Hash,
  }),
  JSON.stringify({
    event: "collector_transferegov_year_completed",
    fiscal_year: 2022,
    coverage_status: "complete",
    distribution_records: 1,
  }),
  JSON.stringify({
    event: "collector_transferegov_year_completed",
    fiscal_year: 2023,
    coverage_status: "empty",
    distribution_records: 0,
  }),
].join("\n");

const executions = [
  {
    fiscalYear: 2022,
    amendmentCode: "202240010001",
    authorKind: "person",
    authorKey: "ana",
    authorName: "Ana",
    authorIdentified: true,
    committedAmount: "100.00",
    effectivePaidAmount: "80.00",
    artifactSha256: aggregateHash,
  },
  {
    fiscalYear: 2023,
    amendmentCode: "202340020001",
    authorKind: "commission",
    authorKey: "comissao-a",
    authorName: "Comissao A",
    authorIdentified: true,
    committedAmount: "50.00",
    effectivePaidAmount: "20.00",
    artifactSha256: aggregateHash,
  },
];

const executionRankings = {
  people: [{
    rankPosition: 1,
    authorKind: "person",
    authorKey: "ana",
    authorName: "Ana",
    amendmentCount: 1,
    committedAmount: "100.00",
    effectivePaidAmount: "80.00",
    firstYear: 2022,
    lastYear: 2022,
  }],
  collectives: [{
    rankPosition: 1,
    authorKind: "commission",
    authorKey: "comissao-a",
    authorName: "Comissao A",
    amendmentCount: 1,
    committedAmount: "50.00",
    effectivePaidAmount: "20.00",
    firstYear: 2023,
    lastYear: 2023,
  }],
};

const documents = [
  {
    archiveYear: 2022,
    amendmentCode: "202240010001",
    documentCode: "NE-1",
    documentDate: "2022-05-01",
    expenseStage: "commitment",
    authorKind: "person",
    authorKey: "ana",
    committedAmount: "100.00",
    paidAmount: "0.00",
    artifactSha256: document2022Hash,
  },
  {
    archiveYear: 2022,
    amendmentCode: "202240010001",
    documentCode: "OB-1",
    documentDate: "2022-06-01",
    expenseStage: "payment",
    authorKind: "person",
    authorKey: "ana",
    committedAmount: "0.00",
    paidAmount: "80.00",
    artifactSha256: document2022Hash,
  },
  {
    archiveYear: 2023,
    amendmentCode: "202340020001",
    documentCode: "NE-2",
    documentDate: "2023-07-01",
    expenseStage: "commitment",
    authorKind: "commission",
    authorKey: "comissao-a",
    committedAmount: "50.00",
    paidAmount: "0.00",
    artifactSha256: document2023Hash,
  },
];

const documentRanking = [
  {
    rankPosition: 1,
    authorKind: "person",
    authorKey: "ana",
    authorName: "Ana",
    amendmentCount: 1,
    documentCount: 2,
    committedAmount: "100.00",
    paidAmount: "80.00",
    firstDocumentDate: "2022-05-01",
    lastDocumentDate: "2022-06-01",
  },
  {
    rankPosition: 2,
    authorKind: "commission",
    authorKey: "comissao-a",
    authorName: "Comissao A",
    amendmentCount: 1,
    documentCount: 1,
    committedAmount: "50.00",
    paidAmount: "0.00",
    firstDocumentDate: "2023-07-01",
    lastDocumentDate: "2023-07-01",
  },
];

const coverage = [
  ["cgu_execution", 2022, "observed", 1],
  ["cgu_execution", 2023, "observed", 1],
  ["cgu_documents", 2022, "observed", 2],
  ["cgu_documents", 2023, "observed", 1],
  ["transferegov_current", 2022, "observed", 1],
  ["transferegov_current", 2023, "empty", 0],
].map(([sourceKey, fiscalYear, coverageStatus, recordCount]) => ({
  sourceKey,
  fiscalYear,
  coverageStatus,
  recordCount,
  lastAttemptedAt: collectedAt,
}));

const currentTransfers = [{ fiscalYear: 2022, externalTransferKey: "current-1" }];

test("RPC federal aplica backoff a indisponibilidade temporaria", async () => {
  let attempts = 0;
  const delays = [];
  const rows = await fetchRpcRows("rpc_teste", {
    baseUrl: "https://project.supabase.co",
    publishableKey: "publishable-key-with-safe-length",
    fetchImpl: async () => {
      attempts += 1;
      if (attempts < 3) return { ok: false, status: 500 };
      return { ok: true, status: 200, json: async () => [] };
    },
    sleepImpl: async (delay) => delays.push(delay),
  });
  assert.deepEqual(rows, []);
  assert.equal(attempts, 3);
  assert.deepEqual(delays, [1_000, 2_000]);
});

test("evidencia federal exige exatamente os eventos executados", () => {
  const evidence = parseFederalCollectorEvidence(collectorLog, notBefore);
  assert.equal(evidence.cguExecution.amendments, 2);
  assert.equal(evidence.cguDocuments.length, 2);
  assert.equal(evidence.transferegovCurrent.length, 2);
  assert.throws(
    () => parseFederalCollectorEvidence(
      collectorLog.replace(aggregateHash, "invalido"),
      notBefore,
    ),
    /evidencia federal da CGU invalida/,
  );
});

test("execucao e documentos da CGU reconciliam seus rankings", () => {
  const evidence = parseFederalCollectorEvidence(collectorLog, notBefore);
  assert.deepEqual(
    verifyCguExecutionProjection(executions, executionRankings, evidence),
    { executions: 2, executionAuthors: 2 },
  );
  assert.deepEqual(
    verifyCguDocumentProjection(documents, documentRanking, evidence),
    { documents: 3, documentAuthors: 2 },
  );
});

test("gate federal bloqueia totais, hashes e cobertura divergentes", () => {
  const evidence = parseFederalCollectorEvidence(collectorLog, notBefore);
  assert.throws(
    () => verifyCguExecutionProjection(
      executions,
      {
        ...executionRankings,
        people: [{ ...executionRankings.people[0], committedAmount: "99.00" }],
      },
      evidence,
    ),
    /total empenhado divergente/,
  );
  assert.throws(
    () => verifyCguDocumentProjection(
      documents.map((row, index) => index === 0
        ? { ...row, artifactSha256: "d".repeat(64) }
        : row),
      documentRanking,
      evidence,
    ),
    /hash documental divergente/,
  );
  assert.throws(
    () => verifyFederalSourceCoverage(
      coverage.map((row) => row.sourceKey === "transferegov_current" &&
          row.fiscalYear === 2022
        ? { ...row, recordCount: 0, coverageStatus: "empty" }
        : row),
      executions,
      documents,
      currentTransfers,
      evidence,
    ),
    /cobertura federal divergente/,
  );
});

test("cobertura federal prova a execucao atual sem apagar fontes independentes", () => {
  const evidence = parseFederalCollectorEvidence(collectorLog, notBefore);
  assert.deepEqual(
    verifyFederalSourceCoverage(
      coverage,
      executions,
      documents,
      currentTransfers,
      evidence,
    ),
    {
      cguExecutionYears: 2,
      cguDocumentYears: 2,
      transferegovYears: 2,
    },
  );
  assert.throws(
    () => verifyFederalSourceCoverage(
      coverage.map((row) => ({ ...row, lastAttemptedAt: "2026-09-03T01:00:00Z" })),
      executions,
      documents,
      currentTransfers,
      evidence,
    ),
    /projecao federal antiga/,
  );
});

test("rankings federais nao aceitam posicoes invertidas com totais corretos", () => {
  const evidence = {
    ...parseFederalCollectorEvidence(collectorLog, notBefore),
    cguExecution: {
      amendments: 2,
      artifactSha256: aggregateHash,
      firstFiscalYear: 2022,
      lastFiscalYear: 2022,
    },
  };
  const rows = [
    executions[0],
    {
      ...executions[0],
      amendmentCode: "202240010002",
      authorKey: "bia",
      authorName: "Bia",
      committedAmount: "90.00",
      effectivePaidAmount: "70.00",
    },
  ];
  const inverted = [
    {
      rankPosition: 1,
      authorKind: "person",
      authorKey: "bia",
      authorName: "Bia",
      amendmentCount: 1,
      committedAmount: "90.00",
      effectivePaidAmount: "70.00",
      firstYear: 2022,
      lastYear: 2022,
    },
    {
      ...executionRankings.people[0],
      rankPosition: 2,
    },
  ];
  assert.throws(
    () => verifyCguExecutionProjection(rows, {
      people: inverted,
      collectives: [],
    }, evidence),
    /ordem do ranking federal divergente/,
  );
  assert.throws(
    () => verifyCguDocumentProjection(
      documents,
      [...documentRanking].reverse().map((row, index) => ({
        ...row,
        rankPosition: index + 1,
      })),
      parseFederalCollectorEvidence(collectorLog, notBefore),
    ),
    /ordem do ranking documental divergente/,
  );
});

test("projecao atual do Transferegov exige contrato editorial completo", () => {
  const row = {
    external_transfer_key: "current-1",
    proposal_id: "proposal-1",
    distribution_id: "distribution-1",
    fiscal_year: 2022,
    author_name: "Ana",
    author_kind: "person",
    destination_amount: "100.00",
    proposal_amount: "100.00",
    committed_amount: "80.00",
    paid_amount: "50.00",
    bank_order_date: "2022-06-01",
    stage_attribution_status: "exact_single_distribution",
    collected_at: collectedAt,
    source_url: "https://transferegov.br/fonte",
    artifact_sha256: aggregateHash,
    methodology_version: "parliamentary-transfers/1.0.0",
  };
  assert.deepEqual(parseCurrentFederalTransferRows([row]), [{
    externalTransferKey: "current-1",
    fiscalYear: 2022,
  }]);
  assert.equal(parseCurrentFederalTransferRows([
    { ...row, methodology_version: "invalida" },
  ]), null);
  assert.equal(parseCurrentFederalTransferRows([row, row]), null);
});

test("Transferegov compara a projecao publica e nao a contagem bruta", () => {
  const evidence = parseFederalCollectorEvidence(
    collectorLog.replace('"distribution_records":1', '"distribution_records":2'),
    notBefore,
  );
  assert.deepEqual(
    verifyFederalSourceCoverage(
      coverage,
      executions,
      documents,
      currentTransfers,
      evidence,
    ),
    {
      cguExecutionYears: 2,
      cguDocumentYears: 2,
      transferegovYears: 2,
    },
  );
  assert.throws(
    () => verifyFederalSourceCoverage(
      coverage,
      executions,
      documents,
      [],
      evidence,
    ),
    /cobertura federal divergente/,
  );
  assert.throws(
    () => verifyFederalSourceCoverage(
      coverage.map((row) => row.sourceKey === "transferegov_current" &&
          row.fiscalYear === 2023
        ? { ...row, coverageStatus: "observed", recordCount: 1 }
        : row),
      executions,
      documents,
      [...currentTransfers, {
        fiscalYear: 2023,
        externalTransferKey: "stale-current-2023",
      }],
      evidence,
    ),
    /coleta vazia do Transferegov manteve registros publicos/,
  );
});
