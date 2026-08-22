import assert from "node:assert/strict";
import test from "node:test";

import {
  EXPENSE_CLASSIFICATION_SOURCE_URL,
  classifyExpenseDescription,
} from "../../apps/web/lib/expense-classification.mjs";

test("completa descrição cortada somente quando o código oficial coincide", () => {
  assert.deepEqual(
    classifyExpenseDescription(
      "3.3.9.0.39.00.00",
      "Outros Servicos Terceiros Pessoa",
    ),
    {
      displayDescription: "Outros Serviços de Terceiros - Pessoa Jurídica",
      sourceDescription: "Outros Servicos Terceiros Pessoa",
      sourceWasTruncated: true,
      classificationStatus: "official_code_match",
    },
  );
  assert.match(EXPENSE_CLASSIFICATION_SOURCE_URL, /^https:\/\/cdn\.tesouro\.gov\.br\//);
});

test("mantém a descrição literal diante de código desconhecido ou conflito", () => {
  assert.equal(
    classifyExpenseDescription("9.9.9.9.99.99.99", "Descrição da Prefeitura")
      .classificationStatus,
    "source_only",
  );
  assert.deepEqual(
    classifyExpenseDescription("3.3.9.0.39.00.00", "Material de Consumo"),
    {
      displayDescription: "Material de Consumo",
      sourceDescription: "Material de Consumo",
      sourceWasTruncated: false,
      classificationStatus: "source_conflict",
    },
  );
});

test("reconhece códigos oficiais confirmados sem alterar valores", () => {
  const cases = new Map([
    ["3.1.9.0.04.00.00", "Contratação por Tempo Determinado"],
    ["3.1.9.0.11.00.00", "Vencimentos e Vantagens Fixas - Pessoal Civil"],
    ["3.3.9.0.30.00.00", "Material de Consumo"],
    ["3.3.9.0.39.00.00", "Outros Serviços de Terceiros - Pessoa Jurídica"],
    ["3.3.9.0.47.00.00", "Obrigações Tributárias e Contributivas"],
    [
      "3.3.9.0.32.00.00",
      "Material, Bem ou Serviço para Distribuição Gratuita",
    ],
    [
      "3.1.9.0.96.00.00",
      "Ressarcimento de Despesas de Pessoal Requisitado",
    ],
    ["3.2.9.0.21.00.00", "Juros sobre a Dívida por Contrato"],
    ["3.2.9.0.22.00.00", "Outros Encargos sobre a Dívida por Contrato"],
    [
      "3.3.9.0.95.00.00",
      "Indenização pela Execução de Trabalhos de Campo",
    ],
    [
      "4.4.9.0.39.00.00",
      "Outros Serviços de Terceiros - Pessoa Jurídica",
    ],
    ["4.6.9.0.71.00.00", "Principal da Dívida Contratual Resgatado"],
    [
      "4.6.9.0.75.00.00",
      "Correção Monetária da Dívida de Operações de Crédito por Antecipação da Receita",
    ],
  ]);

  for (const [code, label] of cases) {
    assert.equal(classifyExpenseDescription(code, label).displayDescription, label);
  }
});
