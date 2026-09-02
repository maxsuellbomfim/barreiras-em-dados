import assert from "node:assert/strict";
import test from "node:test";

import {
  selectFederalRepresentativesForOverview,
  selectStateRepresentativesForOverview,
} from
  "../../apps/web/lib/representative-overview.mjs";

function profile(index) {
  return {
    externalId: `federal-${index}`,
    displayName: `Pessoa ${String(index).padStart(2, "0")}`,
  };
}

function vote(index, overrides = {}) {
  return {
    sourceKind: "federal",
    representativeExternalId: `federal-${index}`,
    electionYear: 2022,
    turnNumber: 1,
    office: "DEPUTADO FEDERAL",
    voteScope: "person",
    votesInBarreiras: index * 100,
    ...overrides,
  };
}

test("recorte federal seleciona os dez atuais mais votados no pleito federal recente", () => {
  const profiles = Array.from({ length: 12 }, (_, index) => profile(index + 1));
  const votes = profiles.map((_, index) => vote(index + 1));

  const selected = selectFederalRepresentativesForOverview(profiles, votes);

  assert.deepEqual(
    selected.map(({ representative }) => representative.externalId),
    [
      "federal-12",
      "federal-11",
      "federal-10",
      "federal-9",
      "federal-8",
      "federal-7",
      "federal-6",
      "federal-5",
      "federal-4",
      "federal-3",
    ],
  );
  assert.equal(selected[0].rankingVote.votesInBarreiras, 1200);
});

test("ranking não soma anos, turnos, outros cargos ou vínculos sem perfil atual", () => {
  const profiles = [profile(1), profile(2), profile(3)];
  const votes = [
    vote(1, { votesInBarreiras: 100 }),
    vote(1, { electionYear: 2018, votesInBarreiras: 50_000 }),
    vote(1, { turnNumber: 2, votesInBarreiras: 40_000 }),
    vote(1, { electionYear: 2024, office: "PREFEITO", votesInBarreiras: 30_000 }),
    vote(2, { votesInBarreiras: 200 }),
    vote(3, { votesInBarreiras: 300 }),
    vote(99, { votesInBarreiras: 90_000 }),
  ];

  const selected = selectFederalRepresentativesForOverview(profiles, votes, 2);

  assert.deepEqual(
    selected.map(({ representative, rankingVote }) => [
      representative.externalId,
      rankingVote.electionYear,
      rankingVote.turnNumber,
      rankingVote.votesInBarreiras,
    ]),
    [
      ["federal-3", 2022, 1, 300],
      ["federal-2", 2022, 1, 200],
    ],
  );
});

test("recorte falha fechado quando não há votação federal individual compatível", () => {
  const selected = selectFederalRepresentativesForOverview(
    [profile(1)],
    [vote(1, { office: "DEPUTADO ESTADUAL" })],
  );

  assert.deepEqual(selected, []);
});

test("recorte estadual seleciona os dez atuais mais votados sem misturar cargo", () => {
  const profiles = Array.from({ length: 12 }, (_, index) => profile(index + 1));
  const votes = profiles.map((_, index) => vote(index + 1, {
    sourceKind: "state",
    office: "DEPUTADO ESTADUAL",
  }));
  votes.push(vote(1, { votesInBarreiras: 99_999 }));

  const selected = selectStateRepresentativesForOverview(profiles, votes);

  assert.deepEqual(
    selected.map(({ representative }) => representative.externalId),
    [
      "federal-12",
      "federal-11",
      "federal-10",
      "federal-9",
      "federal-8",
      "federal-7",
      "federal-6",
      "federal-5",
      "federal-4",
      "federal-3",
    ],
  );
  assert.equal(selected[0].rankingVote.votesInBarreiras, 1200);
});

test("recorte estadual falha fechado sem voto estadual individual do primeiro turno", () => {
  const selected = selectStateRepresentativesForOverview(
    [profile(1)],
    [vote(1, { sourceKind: "state", office: "DEPUTADO ESTADUAL", turnNumber: 2 })],
  );

  assert.deepEqual(selected, []);
});
