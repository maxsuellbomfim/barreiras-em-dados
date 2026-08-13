import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyElectionOutcome,
  electionCycleLabel,
  electionPeriodLabel,
  latestElectionYear,
  outcomeLabel,
} from "../../apps/web/lib/representative-election-context.mjs";

test("classifica somente resultados eleitorais publicados pelo TSE", () => {
  assert.equal(classifyElectionOutcome("ELEITO"), "elected");
  assert.equal(classifyElectionOutcome("ELEITO POR QP"), "elected");
  assert.equal(classifyElectionOutcome("ELEITO POR MÉDIA"), "elected");
  assert.equal(classifyElectionOutcome("SUPLENTE"), "alternate");
  assert.equal(classifyElectionOutcome("NÃO ELEITO"), "not_elected");
  assert.equal(classifyElectionOutcome("2º TURNO"), "other");
  assert.equal(classifyElectionOutcome(null), "unknown");
});

test("traduz a situação sem sugerir mandato atual", () => {
  assert.equal(outcomeLabel("elected"), "Eleito naquele pleito");
  assert.equal(outcomeLabel("alternate"), "Suplente naquele pleito");
  assert.equal(outcomeLabel("not_elected"), "Não eleito naquele pleito");
  assert.equal(outcomeLabel("other"), "Outra situação no pleito");
  assert.equal(outcomeLabel("unknown"), "Situação não informada");
});

test("separa ciclos e períodos eleitorais sem converter candidatura em cargo atual", () => {
  assert.equal(electionCycleLabel(2024, "Vereador"), "Eleição municipal de 2024");
  assert.equal(electionPeriodLabel(2024, "Prefeito"), "ciclo 2025–2028");
  assert.equal(electionCycleLabel(2022, "Deputado Federal"), "Eleição geral de 2022");
  assert.equal(electionPeriodLabel(2022, "Deputado Estadual"), "ciclo 2023–2027");
  assert.equal(electionPeriodLabel(2022, "Governador"), "ciclo 2023–2026");
  assert.equal(electionPeriodLabel(2022, "Senador"), "ciclo 2023–2031");
  assert.equal(electionPeriodLabel(2023, "Cargo desconhecido"), "período decorrente do pleito");
});

test("seleciona por padrão a eleição mais recente disponível", () => {
  assert.equal(latestElectionYear([2022, 2024, 2020, 2024]), "2024");
  assert.equal(latestElectionYear([]), "todos");
});
