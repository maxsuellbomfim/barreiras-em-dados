import assert from "node:assert/strict";
import test from "node:test";

import {
  isMonthlyFinanceCommentaryCompatible,
} from "../../apps/web/lib/monthly-finance-commentary.mjs";

test("recusa comentário antigo que contradiz um fechamento operacional", () => {
  for (const commentary of [
    "Os relatórios comparáveis ainda não estão disponíveis.",
    "O mês aguarda os relatórios necessários para comparação.",
    "Ainda faltam dados para concluir a leitura do período.",
  ]) {
    assert.equal(
      isMonthlyFinanceCommentaryCompatible("operational", commentary),
      false,
      commentary,
    );
  }
});

test("mantém comentário compatível com o fechamento operacional", () => {
  assert.equal(
    isMonthlyFinanceCommentaryCompatible(
      "operational",
      "Os relatórios do período foram comparados e a diferença operacional pode ser conferida nas fontes.",
    ),
    true,
  );
});

test("não interfere no comentário de um mês que realmente precisa de dados", () => {
  assert.equal(
    isMonthlyFinanceCommentaryCompatible(
      "needs_data",
      "Os relatórios comparáveis ainda não estão disponíveis.",
    ),
    true,
  );
});
