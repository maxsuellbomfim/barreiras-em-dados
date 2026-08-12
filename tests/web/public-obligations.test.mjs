import assert from "node:assert/strict";
import test from "node:test";

import { getPublicObligations } from "../../apps/web/lib/public-obligations.mjs";

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
