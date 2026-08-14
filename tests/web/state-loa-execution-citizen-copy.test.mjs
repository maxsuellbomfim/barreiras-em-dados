import assert from "node:assert/strict";
import test from "node:test";

const copyModule = await import(
  "../../apps/web/lib/state-loa-execution-citizen-copy.mjs"
).catch(() => ({ stateLoaExecutionStatusCopy: () => null }));

const { stateLoaExecutionStatusCopy } = copyModule;

test("explica valor zero publicado sem confundi-lo com dado ausente", () => {
  assert.deepEqual(
    stateLoaExecutionStatusCopy({
      executionStatus: "execution_confirmed",
      loaScopeOccurrences: 1,
      executionOccurrences: 1,
      paidAmount: "0.00",
    }),
    {
      tone: "confirmed",
      label: "Execução encontrada",
      explanation:
        "A autorização foi ligada a uma única linha da execução estadual. Valores de R$ 0,00 são os publicados pela própria fonte neste retrato, não campos ausentes.",
    },
  );
});

test("colisão oficial permanece sem valores e explica por que não houve ligação", () => {
  assert.deepEqual(
    stateLoaExecutionStatusCopy({
      executionStatus: "ambiguous_official_key",
      loaScopeOccurrences: 17,
      executionOccurrences: 1,
      paidAmount: null,
    }),
    {
      tone: "pending",
      label: "Ligação ambígua",
      explanation:
        "A mesma chave aparece 17 vezes na LOA e 1 vez na execução. Não atribuímos empenho, liquidação ou pagamento a esta emenda sem uma chave oficial exclusiva.",
    },
  );
});

test("ausência na execução é descrita como limite da consulta, nunca como zero", () => {
  assert.deepEqual(
    stateLoaExecutionStatusCopy({
      executionStatus: "not_found_in_execution_source",
      loaScopeOccurrences: 1,
      executionOccurrences: 0,
      paidAmount: null,
    }),
    {
      tone: "not-found",
      label: "Não encontrada na execução consultada",
      explanation:
        "A autorização consta na LOA, mas nenhuma linha correspondente foi localizada no retrato estadual consultado. Isso não significa pagamento zero nem ausência definitiva.",
    },
  );
});

test("ano ainda sem índice de escopo não fabrica conclusão financeira", () => {
  assert.deepEqual(
    stateLoaExecutionStatusCopy({
      executionStatus: "scope_not_available",
      loaScopeOccurrences: 0,
      executionOccurrences: 0,
      paidAmount: null,
    }),
    {
      tone: "unavailable",
      label: "Cruzamento ainda indisponível",
      explanation:
        "Este exercício ainda não possui índice estadual completo para uma ligação segura. A autorização continua visível, mas os estágios de execução permanecem sem atribuição.",
    },
  );
});
