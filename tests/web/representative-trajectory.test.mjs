import assert from "node:assert/strict";
import test from "node:test";

import { buildRepresentativeTrajectory } from "../../apps/web/lib/representative-trajectory.mjs";

const currentMandate = {
  office: "Deputado federal em exercício",
  period: "57ª legislatura",
  status: "Exercício · condição eleitoral atual: Suplente",
  sourceLabel: "Câmara dos Deputados",
  sourceUrl: "https://www.camara.leg.br/deputados/123",
};

const stateCandidacy = {
  electionYear: 2018,
  turnNumber: 1,
  office: "Deputado Estadual",
  candidateId: "candidate-2018",
  situation: "NÃO ELEITO",
  votesInBarreiras: 4321,
  voteScope: "person",
  evidenceUrl: "https://divulgacandcontas.tse.jus.br/",
};

const federalCandidacy = {
  electionYear: 2022,
  turnNumber: 1,
  office: "Deputado Federal",
  candidateId: "candidate-2022",
  situation: "SUPLENTE",
  votesInBarreiras: 8765,
  voteScope: "person",
  evidenceUrl: "https://divulgacandcontas.tse.jus.br/",
};

test("organiza candidaturas por data e encerra com a situação atual oficial", () => {
  const events = buildRepresentativeTrajectory({
    currentMandate,
    electionEvents: [federalCandidacy, stateCandidacy],
  });

  assert.deepEqual(
    events.map((event) => [event.kind, event.heading, event.status]),
    [
      ["election", "Candidatura a Deputado Estadual", "Não eleito naquele pleito"],
      ["election", "Candidatura a Deputado Federal", "Suplente naquele pleito"],
      ["current", "Deputado federal em exercício", "Exercício · condição eleitoral atual: Suplente"],
    ],
  );
});

test("preserva mudança de cargo sem transformar candidatura antiga em mandato atual", () => {
  const events = buildRepresentativeTrajectory({
    currentMandate,
    electionEvents: [stateCandidacy],
  });

  assert.equal(events[0].heading, "Candidatura a Deputado Estadual");
  assert.equal(events[0].period, "Eleição geral de 2018 · ciclo 2019–2023 · 1º turno");
  assert.equal(events[0].detail, "4.321 votos em Barreiras");
  assert.equal(events[0].sourceLabel, "TSE");
  assert.equal(events[1].heading, "Deputado federal em exercício");
});

test("mantém o mandato atual visível mesmo sem candidatura vinculada", () => {
  const events = buildRepresentativeTrajectory({
    currentMandate,
    electionEvents: [],
  });

  assert.deepEqual(events, [
    {
      key: "current",
      kind: "current",
      heading: "Deputado federal em exercício",
      period: "57ª legislatura",
      status: "Exercício · condição eleitoral atual: Suplente",
      detail: "Situação atual publicada pela fonte oficial",
      sourceLabel: "Câmara dos Deputados",
      sourceUrl: "https://www.camara.leg.br/deputados/123",
    },
  ]);
});
