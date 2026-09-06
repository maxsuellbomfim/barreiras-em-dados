import assert from "node:assert/strict";
import test from "node:test";
import { loadReviewedFnsLinks } from "../../apps/web/lib/fns-reviewed-links.mjs";

const code = "257001000012025OB055607";
const sha = "a".repeat(64);
const document = {
  documentCode: code, artifactSha256: sha, expenseStage: "payment",
  authorKind: "commission", authorName: "COM. DA SAUDE", paidAmount: "5000000.00",
};
const row = {
  document_code: code, cgu_archive_sha256: sha, requester_name: "PARLAMENTAR EXEMPLO",
  fns_author_name: "COMISSÃO DA SAÚDE", payment_sha256: "b".repeat(64),
  order_sha256: "c".repeat(64), source_url: "https://consultafns.saude.gov.br/#/detalhada",
  reviewed_at: "2026-09-06T01:00:00Z", methodology_version: "fns-cgu-reviewed-links/1.0.0",
};

test("consulta uma vez apenas pagamentos elegíveis da página e minimiza campos", async () => {
  const calls = [];
  const before = JSON.stringify(document);
  const result = await loadReviewedFnsLinks([document], async (codes) => {
    calls.push(codes);
    return [{ ...row, bank_account: "PRIVATE", paid_amount: "99999999", private_id: "PRIVATE" }];
  });
  assert.deepEqual(calls, [[code]]);
  assert.equal(result.state, "available");
  assert.equal(result.links[0].requesterName, row.requester_name);
  assert.equal(JSON.stringify(document), before);
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE|99999999|paidAmount/);
});

test("nenhuma aprovação não significa ausência de solicitante", async () => {
  assert.deepEqual(await loadReviewedFnsLinks([document], async () => []),
    { state: "available", links: [] });
});

test("falha complementar não lança erro nem modifica documentos financeiros", async () => {
  for (const call of [async () => null, async () => { throw Error("PRIVATE"); }]) {
    assert.deepEqual(await loadReviewedFnsLinks([document], call), { state: "unavailable", links: [] });
  }
});

test("não atribui solicitante quando o retrato CGU do cartão é diferente", async () => {
  const result = await loadReviewedFnsLinks([document], async () => [{ ...row, cgu_archive_sha256: "d".repeat(64) }]);
  assert.deepEqual(result, { state: "available", links: [] });
});

test("rejeita resposta duplicada, malformada, fonte ou documento fora do escopo", async () => {
  for (const rows of [
    [row, row], [{ ...row, source_url: "https://evil.example" }],
    [{ ...row, document_code: "257001000012025OB059959" }],
    [{ ...row, requester_name: "123.456.789-01" }],
    [{ ...row, methodology_version: "unknown" }],
    [{ ...row, reviewed_at: "bad-date" }],
    [{ ...row, payment_sha256: null }],
  ]) {
    assert.deepEqual(await loadReviewedFnsLinks([document], async () => rows), { state: "unavailable", links: [] });
  }
});

test("não consulta nem associa empenhos, autoria individual ou linhas duplicadas", async () => {
  const fail = async () => { assert.fail("RPC não deveria ser chamada"); };
  for (const docs of [[], [{ ...document, expenseStage: "commitment" }],
    [{ ...document, authorKind: "person" }], [document, { ...document }]]) {
    assert.deepEqual(await loadReviewedFnsLinks(docs, fail), { state: "available", links: [] });
  }
});

test("limita o lote sem truncar silenciosamente mais de cinquenta cartões", async () => {
  assert.deepEqual(await loadReviewedFnsLinks(Array(51).fill(document), async () => []), { state: "unavailable", links: [] });
});
