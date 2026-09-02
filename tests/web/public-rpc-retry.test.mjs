import assert from "node:assert/strict";
import test from "node:test";

import { fetchPublicRpcRows } from "../../apps/web/lib/public-rpc.mjs";

const request = {
  url: "https://example.supabase.co/rest/v1/rpc/example",
  headers: { apikey: "sb_publishable_fixture" },
  body: "{}",
};

test("RPC pública repete uma falha HTTP transitória sem reutilizar o cache", async () => {
  const calls = [];
  const responses = [
    new Response('{"message":"temporary"}', { status: 500 }),
    Response.json([{ id: 1 }]),
  ];
  const rows = await fetchPublicRpcRows(request, {
    fetchImpl: async (_url, init) => {
      calls.push(init);
      return responses.shift();
    },
  });

  assert.deepEqual(rows, [{ id: 1 }]);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].next, { revalidate: 300 });
  assert.equal(calls[0].cache, undefined);
  assert.equal(calls[1].cache, "no-store");
  assert.equal(calls[1].next, undefined);
});

test("RPC pública repete uma exceção transitória uma única vez", async () => {
  let attempts = 0;
  const rows = await fetchPublicRpcRows(request, {
    fetchImpl: async () => {
      attempts += 1;
      if (attempts === 1) throw new DOMException("timeout", "TimeoutError");
      return Response.json([{ id: 2 }]);
    },
  });

  assert.deepEqual(rows, [{ id: 2 }]);
  assert.equal(attempts, 2);
});

test("RPC pública não repete erro definitivo nem aceita payload inválido", async () => {
  let permanentAttempts = 0;
  const permanent = await fetchPublicRpcRows(request, {
    fetchImpl: async () => {
      permanentAttempts += 1;
      return new Response('{"message":"bad request"}', { status: 400 });
    },
  });
  const malformed = await fetchPublicRpcRows(request, {
    fetchImpl: async () => Response.json({ id: 3 }),
  });

  assert.equal(permanent, null);
  assert.equal(permanentAttempts, 1);
  assert.equal(malformed, null);
});
