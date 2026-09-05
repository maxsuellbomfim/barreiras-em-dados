import assert from "node:assert/strict";
import test from "node:test";
import { getIntegralGazetteEditions } from "../../apps/web/lib/integral-gazette-documents.ts";

function edition(number) {
  return {
    edition: number, edition_year: 2026, edition_date: "2026-02-13",
    artifact_sha256: "a".repeat(64), methodology_version: "integral-gazette-documents/1.0.0",
    documents: [{
      document_id: `doc-${number}`, document_order: 1,
      literal_title: "Portaria", document_type: "portaria", page_start: 1, page_end: 1,
      full_text: "Portaria. Texto oficial completo.", text_sha256: "b".repeat(64),
      publication_status: "validated",
    }],
  };
}

test("cliente preserva prioridade e paginação determinadas pela busca no banco", async (t) => {
  const previousUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const previousKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  t.after(() => {
    if (previousUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = previousUrl;
    if (previousKey === undefined) delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    else process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = previousKey;
  });
  let requested;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    requested = { url, body: JSON.parse(init.body) };
    // Edição exata vem primeiro; a edição posterior apenas menciona o número.
    return new Response(JSON.stringify([edition(4598), edition(4600)]));
  });
  const result = await getIntegralGazetteEditions({query: "4598", pageSize: 1});
  assert.equal(result.state, "available");
  assert.deepEqual(result.editions.map((row) => row.edition), [4598]);
  assert.equal(result.hasMore, true);
  assert.equal(result.offset, 0);
  assert.match(requested.url, /\/search_integral_gazette_editions$/);
  assert.deepEqual(requested.body, {query_text: "4598", page_size: 2, page_offset: 0});
});
