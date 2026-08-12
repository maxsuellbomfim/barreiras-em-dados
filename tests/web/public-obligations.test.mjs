import assert from "node:assert/strict";
import test from "node:test";

import {
  getPublicObligationCoverage,
  getPublicObligations,
} from "../../apps/web/lib/public-obligations.mjs";

const originalFetch = globalThis.fetch;
const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;

function validRow() {
  return {
    obligation_id: "00000000-0000-4000-8000-000000000931",
    obligation_type: "restos_a_pagar_total",
    description: "Pagamentos de restos a pagar informados no balancete mensal",
    fiscal_year: 2026,
    period_start: "2026-06-01",
    period_end: "2026-06-30",
    opening_balance: null,
    additions_amount: null,
    reductions_amount: null,
    payments_prior_amount: "45364644.06",
    payments_amount: "3683221.97",
    payments_to_date_amount: "49047866.03",
    closing_balance: null,
    status: "reported",
    validation_state: "validated",
    source_url: "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=balancetes",
    artifact_sha256: "a".repeat(64),
    source_retrieved_at: "2026-08-11T16:40:00.000Z",
    document_source_url:
      "https://barreiras.mtransparente.com.br/balancete-junho-2026.pdf",
    document_artifact_sha256: "b".repeat(64),
    document_retrieved_at: "2026-08-11T16:41:00.000Z",
    methodology_version: "public-obligations-balancete/1.0.0",
  };
}

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
});

test("carrega pagamento mensal de restos a pagar sem convertê-lo em dívida total", async () => {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => [validRow()],
  });

  const result = await getPublicObligations();

  assert.equal(result.state, "available");
  assert.equal(result.obligations.length, 1);
  assert.equal(result.obligations[0].paymentsPeriodAmount, "3683221.97");
  assert.equal(result.obligations[0].paymentsToDateAmount, "49047866.03");
  assert.equal("totalDebt" in result.obligations[0], false);
});

test("normaliza decimais numéricos retornados pelo PostgREST sem rejeitar centavos válidos", async () => {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => [
      {
        ...validRow(),
        fiscal_year: 2021,
        period_start: "2021-02-01",
        period_end: "2021-02-28",
        payments_prior_amount: 18542319.37,
        payments_amount: 2467434.19,
        payments_to_date_amount: 21009753.56,
      },
    ],
  });

  const result = await getPublicObligations();

  assert.equal(result.state, "available");
  assert.equal(result.obligations[0].paymentsPriorAmount, "18542319.37");
  assert.equal(result.obligations[0].paymentsPeriodAmount, "2467434.19");
  assert.equal(result.obligations[0].paymentsToDateAmount, "21009753.56");
});

test("falha fechada quando a progressão dos pagamentos diverge", async () => {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => [{ ...validRow(), payments_to_date_amount: "49047866.04" }],
  });

  assert.deepEqual(await getPublicObligations(), { state: "unavailable" });
});

test("expõe ausência e incompletude comprovadas sem convertê-las em zero", async () => {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  globalThis.fetch = async (_url, request) => {
    assert.deepEqual(JSON.parse(request.body), {
      page_size: 120,
      fiscal_year_from: 2021,
      fiscal_year_to: null,
    });
    return {
      ok: true,
      json: async () => [
        {
          coverage_id: "public-obligation-coverage:2022-02",
          fiscal_year: 2022,
          period_start: "2022-02-01",
          period_end: "2022-02-28",
          coverage_status: "section_absent",
          source_url: "https://barreiras.mtransparente.com.br/balancete-fevereiro-2022.pdf",
          document_artifact_sha256: "c".repeat(64),
          checked_at: "2026-08-12T01:55:57.000Z",
          search_evidence_sha256: null,
          evidence_artifact_count: null,
          methodology_version: "public-obligation-coverage/1.1.0",
        },
        {
          coverage_id: "public-obligation-coverage:2022-03",
          fiscal_year: 2022,
          period_start: "2022-03-01",
          period_end: "2022-03-31",
          coverage_status: "document_not_found",
          source_url:
            "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=balancetes&limit=500&offset=0",
          document_artifact_sha256: null,
          search_evidence_sha256: "d".repeat(64),
          evidence_artifact_count: 1,
          checked_at: "2026-08-12T02:20:00.000Z",
          methodology_version: "public-obligation-coverage/1.1.0",
        },
      ],
    };
  };

  const result = await getPublicObligationCoverage();

  assert.equal(result.state, "available");
  assert.equal(result.rows[0].coverageStatus, "section_absent");
  assert.equal(result.rows[0].amount, undefined);
  assert.equal(result.rows[1].coverageStatus, "document_not_found");
  assert.equal(result.rows[1].documentArtifactSha256, null);
  assert.equal(result.rows[1].searchEvidenceSha256, "d".repeat(64));
  assert.equal(result.rows[1].evidenceArtifactCount, 1);
});

test("falha fechada quando a cobertura pública tenta expor estado interno", async () => {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => [
      {
        coverage_id: "public-obligation-coverage:2022-09",
        fiscal_year: 2022,
        period_start: "2022-09-01",
        period_end: "2022-09-30",
        coverage_status: "ocr_failed",
        source_url: null,
        document_artifact_sha256: null,
        checked_at: null,
        methodology_version: "public-obligation-coverage/1.0.0",
      },
    ],
  });

  assert.deepEqual(await getPublicObligationCoverage(), { state: "unavailable" });
});
