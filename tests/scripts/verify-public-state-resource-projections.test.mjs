import assert from "node:assert/strict";
import test from "node:test";

import {
  fetchAllRpcRows,
  parseCollectorEvidence,
  verifyLoaProjection,
  verifyPublicProjection,
  verifySpecialTransferProjection,
  verifyStateExecutionProjection,
} from "../../scripts/verify-public-state-resource-projections.mjs";

const stateExecutionCoverage = [
  {
    fiscalYear: 2022,
    sourceAggregateCount: 449,
    sourceArtifactSha256: "a".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
  {
    fiscalYear: 2021,
    sourceAggregateCount: 530,
    sourceArtifactSha256: "a".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
];

const loaCoverage = [
  {
    fiscalYear: 2022,
    loaStatus: "observed",
    amendmentCount: 2,
    lastAttemptedAt: "2026-09-03T22:01:00Z",
  },
  {
    fiscalYear: 2021,
    loaStatus: "blocked",
    amendmentCount: null,
    lastAttemptedAt: "2026-09-03T22:01:00Z",
  },
];

const specialCoverage = [
  {
    fiscalYear: 2022,
    sourcePaymentCount: 250,
    territorialPaymentCount: 3,
    sourceArtifactSha256: "b".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
  {
    fiscalYear: 2021,
    sourcePaymentCount: 119,
    territorialPaymentCount: 0,
    sourceArtifactSha256: "b".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
];

const specialPayments = [
  {
    fiscalYear: 2022,
    paymentId: "payment-1",
    authorKey: "author-1",
    associationStatus: "approved_official_author_code_crosswalk",
    officialAmendmentCode: "407200032021",
    paymentAmount: "594841.25",
    paymentDate: "2022-05-10",
    sourceArtifactSha256: "b".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
  {
    fiscalYear: 2022,
    paymentId: "payment-2",
    authorKey: "author-1",
    associationStatus: "approved_official_author_code_crosswalk",
    officialAmendmentCode: "407200052021",
    paymentAmount: "75300.00",
    paymentDate: "2022-06-01",
    sourceArtifactSha256: "b".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
  {
    fiscalYear: 2022,
    paymentId: "payment-3",
    authorKey: "author-1",
    associationStatus: "approved_official_author_code_crosswalk",
    officialAmendmentCode: "407200052021",
    paymentAmount: "86763.50",
    paymentDate: "2022-06-02",
    sourceArtifactSha256: "b".repeat(64),
    sourceCollectedAt: "2026-09-03T22:00:00Z",
  },
];

const specialRanking = [
  {
    rankPosition: 1,
    authorKey: "author-1",
    paymentCount: 3,
    amendmentCount: 2,
    paidAmount: "756904.75",
    firstPaymentDate: "2022-05-10",
    lastPaymentDate: "2022-06-02",
  },
];

test("projecao estadual exige cobertura de fonte observada", () => {
  assert.deepEqual(
    verifyStateExecutionProjection(stateExecutionCoverage, {
      artifactSha256: "a".repeat(64),
    }),
    { years: 2, sourceRecords: 979 },
  );
  assert.throws(
    () => verifyStateExecutionProjection([]),
    /nenhum exercicio estadual publicado/,
  );
});

test("projecao da LOA cobre exatamente os mesmos exercicios da execucao", () => {
  assert.deepEqual(
    verifyLoaProjection(loaCoverage, stateExecutionCoverage),
    { years: 2, observedYears: 1, blockedYears: 1 },
  );
  assert.throws(
    () => verifyLoaProjection(loaCoverage.slice(0, 1), stateExecutionCoverage),
    /exercicios divergentes/,
  );
  assert.throws(
    () => verifyLoaProjection(loaCoverage, stateExecutionCoverage, {
      years: [
        { fiscalYear: 2021, collectionStatus: "blocked" },
        { fiscalYear: 2022, collectionStatus: "complete" },
      ],
      notBefore: "2026-09-04T22:00:00Z",
    }),
    /projecao antiga da LOA/,
  );
});

test("LOA coletada pode ser publicada como vazia quando nao ha linha territorial", () => {
  const coverageWithoutBarreiras = loaCoverage.map((row) => row.fiscalYear === 2022
    ? { ...row, loaStatus: "empty", amendmentCount: 0 }
    : row);
  assert.deepEqual(
    verifyLoaProjection(coverageWithoutBarreiras, stateExecutionCoverage, {
      years: [
        { fiscalYear: 2021, collectionStatus: "blocked" },
        { fiscalYear: 2022, collectionStatus: "complete" },
      ],
      notBefore: "2026-09-03T22:00:00Z",
    }),
    { years: 2, observedYears: 0, blockedYears: 1 },
  );
});

test("pagamentos especiais reconciliam cobertura e ranking sem valores fixos", () => {
  assert.deepEqual(
    verifySpecialTransferProjection({
      coverage: specialCoverage,
      payments: specialPayments,
      ranking: specialRanking,
    }),
    {
      years: 2,
      territorialPayments: 3,
      rankedAuthors: 1,
      unlinkedPayments: 0,
    },
  );
});

test("pagamentos especiais bloqueiam falso verde por contagem ou ranking divergente", () => {
  assert.throws(
    () => verifySpecialTransferProjection({
      coverage: [
        { ...specialCoverage[0], territorialPaymentCount: 2 },
        specialCoverage[1],
      ],
      payments: specialPayments,
      ranking: specialRanking,
    }),
    /contagem territorial divergente/,
  );

  assert.throws(
    () => verifySpecialTransferProjection({
      coverage: specialCoverage,
      payments: specialPayments.map((payment, index) => index === 0
        ? { ...payment, sourceArtifactSha256: "c".repeat(64) }
        : payment),
      ranking: specialRanking,
    }),
    /linhagem divergente/,
  );

  assert.throws(
    () => verifySpecialTransferProjection({
      coverage: specialCoverage,
      payments: specialPayments,
      ranking: [{ ...specialRanking[0], paidAmount: "1.00" }],
    }),
    /total pago divergente/,
  );
});

test("pagamentos especiais nao aceitam apagar toda a evidencia territorial", () => {
  assert.throws(
    () => verifySpecialTransferProjection({
      coverage: specialCoverage.map((row) => ({
        ...row,
        territorialPaymentCount: 0,
      })),
      payments: [],
      ranking: [],
    }),
    /nenhum pagamento territorial publicado/,
  );
});

test("gate consulta a RPC publica sem cache e valida o contrato antes de passar", async () => {
  const requests = [];
  const result = await verifyPublicProjection("state-execution", {
    baseUrl: "https://example.supabase.co",
    publishableKey: "sb_publishable_1234567890",
    collectorEvidence: { artifactSha256: "a".repeat(64) },
    fetchImpl: async (url, init) => {
      requests.push({ url, init });
      return Response.json([{
        fiscal_year: 2022,
        source_aggregate_count: 449,
        source_author_count: 63,
        territorial_key_status: "territorial_key_unavailable_in_source",
        source_snapshot_status: "source_snapshot_observed",
        source_url: "https://dados.ba.gov.br/source",
        source_artifact_sha256: "a".repeat(64),
        source_collected_at: "2026-09-03T22:00:00Z",
        methodology_version: "bahia-state-execution-source-coverage/1.0.0",
      }]);
    },
  });

  assert.deepEqual(result, { years: 1, sourceRecords: 449 });
  assert.equal(
    requests[0].url,
    "https://example.supabase.co/rest/v1/rpc/" +
      "get_public_bahia_state_execution_annual_coverage",
  );
  assert.equal(requests[0].init.cache, "no-store");
  assert.equal(requests[0].init.headers["accept-profile"], "api");
  assert.equal(requests[0].init.headers.apikey, "sb_publishable_1234567890");
});

test("evidencia do coletor usa o hash atual e estados anuais da LOA", () => {
  assert.deepEqual(
    parseCollectorEvidence(
      "state-execution",
      JSON.stringify({
        event: "collector_bahia_state_amendments_completed",
        artifact_hash: "a".repeat(64),
      }),
    ),
    { artifactSha256: "a".repeat(64) },
  );
  assert.deepEqual(
    parseCollectorEvidence(
      "loa",
      [
        JSON.stringify({
          event: "collector_bahia_state_loa_year_completed",
          fiscal_year: 2021,
          coverage_status: "blocked",
        }),
        JSON.stringify({
          event: "collector_bahia_state_loa_year_completed",
          fiscal_year: 2022,
          coverage_status: "complete",
        }),
      ].join("\n"),
      "2026-09-03T22:00:00Z",
    ),
    {
      years: [
        { fiscalYear: 2021, collectionStatus: "blocked" },
        { fiscalYear: 2022, collectionStatus: "complete" },
      ],
      notBefore: "2026-09-03T22:00:00Z",
    },
  );
});

test("paginacao publica percorre todas as paginas sem truncar", async () => {
  const offsets = [];
  const rows = await fetchAllRpcRows("example_rpc", {
    baseUrl: "https://example.supabase.co",
    publishableKey: "sb_publishable_1234567890",
    fetchImpl: async (_url, init) => {
      const body = JSON.parse(init.body);
      offsets.push(body.page_offset);
      return Response.json(body.page_offset === 0
        ? [{ id: 1 }, { id: 2 }]
        : [{ id: 3 }]);
    },
  }, {
    pageSize: 2,
    body: { fiscal_year_filter: null },
  });

  assert.deepEqual(rows, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  assert.deepEqual(offsets, [0, 2]);
});

test("gate pede os limites maximos e exige a mesma linhagem especial", async () => {
  const sourceHash = "b".repeat(64);
  const collectedAt = "2026-09-03T22:00:00Z";
  const bodies = new Map();
  const rawPayment = {
    fiscal_year: 2022,
    amendment_number: "40720003",
    amendment_year: 2021,
    official_amendment_code: "202140720003",
    source_author_name: "AUTOR OFICIAL",
    author_key: "autor-1",
    official_author_name: "Autor Oficial",
    representative_source_kind: "state",
    representative_external_id: "1",
    representative_profile_url: "https://www.al.ba.gov.br/deputados/1",
    association_status: "approved_official_author_code_crosswalk",
    agency_name: "SECRETARIA",
    budget_unit_name: "UNIDADE ORCAMENTARIA",
    action_name: "Apoio financeiro",
    payment_id: "202240720003000001",
    payment_number: "1234",
    payment_date: "2022-10-05",
    payment_amount: "10.00",
    payment_status: "Sim",
    object_text: "Objeto no municipio de Barreiras",
    payment_url: "https://www.transparencia.ba.gov.br/Pagamento/1234",
    financial_stage: "paid_by_bahia_state",
    territorial_scope: "payment_object_literal_barreiras",
    federal_link_status: "not_found_in_cgu",
    aggregation_policy: "single_source_no_cross_source_sum",
    evidence_text: "Barreiras - objeto oficial",
    evidence_sha256: "a".repeat(64),
    source_url: "https://dados.ba.gov.br/dataset/transferencias-especiais",
    source_artifact_sha256: sourceHash,
    source_collected_at: collectedAt,
    methodology_version: "bahia-special-transfer-payments/1.0.0",
  };
  const rawCoverage = {
    fiscal_year: 2022,
    source_payment_count: 250,
    territorial_payment_count: 1,
    territorial_status: "territorial_records_observed",
    source_snapshot_status: "source_snapshot_processed",
    territorial_scope: "payment_object_literal_barreiras",
    source_url: "https://dados.ba.gov.br/dataset/transferencias-especiais",
    source_artifact_sha256: sourceHash,
    source_collected_at: collectedAt,
    methodology_version: "bahia-special-transfer-annual-coverage/1.0.0",
  };
  const rawRanking = {
    rank_position: 1,
    author_key: "autor-1",
    official_author_name: "Autor Oficial",
    representative_source_kind: "state",
    representative_external_id: "1",
    representative_profile_url: "https://www.al.ba.gov.br/deputados/1",
    payment_count: 1,
    amendment_count: 1,
    paid_amount: "10.00",
    first_payment_date: "2022-10-05",
    last_payment_date: "2022-10-05",
    ranking_amount_stage: "paid_by_bahia_state",
    territorial_scope: "payment_object_literal_barreiras",
    aggregation_policy: "single_source_no_cross_source_sum",
    methodology_version: "bahia-special-transfer-ranking/1.0.0",
  };

  const result = await verifyPublicProjection("special-transfers", {
    baseUrl: "https://example.supabase.co",
    publishableKey: "sb_publishable_1234567890",
    collectorEvidence: { artifactSha256: sourceHash },
    fetchImpl: async (url, init) => {
      const body = JSON.parse(init.body);
      bodies.set(`${url}:${body.page_offset ?? "single"}`, body);
      if (url.includes("annual_coverage")) return Response.json([rawCoverage]);
      if (url.includes("payments")) {
        return Response.json(body.page_offset === 0 ? [rawPayment] : []);
      }
      return Response.json(body.page_offset === 0 ? [rawRanking] : []);
    },
  });

  assert.deepEqual(result, {
    years: 1,
    territorialPayments: 1,
    rankedAuthors: 1,
    unlinkedPayments: 0,
  });
  assert.deepEqual(
    [...bodies].find(([key]) => key.includes("transfer_payments:0"))?.[1],
    {
      page_offset: 0,
      fiscal_year_filter: null,
      author_key_filter: null,
      page_size: 200,
    },
  );
  assert.deepEqual(
    [...bodies].find(([key]) => key.includes("transfer_ranking:0"))?.[1],
    { page_offset: 0, fiscal_year_filter: null, page_size: 50 },
  );
});
