import assert from "node:assert/strict";
import test from "node:test";

import { formatCollectionWorkProgress } from "../../apps/admin/app/collection-work-progress.mjs";

test("traduz progresso retomável sem expor o cursor da partição", () => {
  assert.deepEqual(
    formatCollectionWorkProgress({
      latest_work_completed: 200,
      latest_work_total: 602,
      latest_work_remaining: 402,
      latest_batch_processed: 100,
    }),
    {
      completed: "200 de 602 itens concluídos",
      remaining: "402 itens ainda aguardam coleta",
      latestBatch: "Último lote: 100 itens",
      percent: 33.22,
    },
  );
});

test("explica a preservação documental do TCM-BA em linguagem específica", () => {
  assert.deepEqual(
    formatCollectionWorkProgress({
      latest_work_completed: 287,
      latest_work_total: 1505,
      latest_work_remaining: 1218,
      latest_batch_processed: 10,
      latest_work_unit: "document",
    }),
    {
      heading: "Progresso documental",
      completed: "287 de 1.505 documentos preservados",
      remaining: "1.218 documentos ainda aguardam preservação",
      latestBatch: "Último lote: 10 documentos",
      percent: 19.07,
    },
  );
});

test("falha fechado diante de progresso ausente ou incoerente", () => {
  assert.equal(
    formatCollectionWorkProgress({
      latest_work_completed: null,
      latest_work_total: null,
      latest_work_remaining: null,
      latest_batch_processed: null,
    }),
    null,
  );
  assert.equal(
    formatCollectionWorkProgress({
      latest_work_completed: 201,
      latest_work_total: 602,
      latest_work_remaining: 402,
      latest_batch_processed: 100,
    }),
    null,
  );
});
