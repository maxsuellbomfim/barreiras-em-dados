import assert from "node:assert/strict";
import test from "node:test";

import {
  legislatureRankingForRepresentative,
} from "../../apps/web/lib/parliamentary-legislature-rankings.mjs";

const ranked = {
  sphere: "state",
  legislatureNumber: 20,
  legislatureLabel: "20ª Legislatura da Assembleia Legislativa da Bahia",
  beginsOn: "2023-02-01",
  endsOn: "2027-01-31",
  fullFiscalYearFrom: 2024,
  fullFiscalYearTo: 2026,
  officialSourceUrl: "https://www.al.ba.gov.br/midia-center/noticias/55953",
  officialSourceNote: "A ALBA registra o início da legislatura.",
  excludedTransitionYears: [2023],
  rankingAmountStage: "authorized",
  rankPosition: 2,
  authorKey: "deputado exemplo",
  authorName: "Deputado Exemplo",
  representativeSourceKind: "state",
  representativeExternalId: "921264",
  representativeProfileUrl:
    "https://www.al.ba.gov.br/deputados/deputado-estadual/921264",
  associationStatus: "approved_official_crosswalk",
  amendmentCount: 3,
  rankingAmount: "500000.00",
  committedAmount: "200000.00",
  liquidatedAmount: "150000.00",
  paidAmount: "100000.00",
  firstYear: 2024,
  lastYear: 2026,
  methodologyVersion: "parliamentary-legislature-transfer-ranking/1.0.0",
};

const groups = [{
  sphere: ranked.sphere,
  legislatureNumber: ranked.legislatureNumber,
  legislatureLabel: ranked.legislatureLabel,
  beginsOn: ranked.beginsOn,
  endsOn: ranked.endsOn,
  fullFiscalYearFrom: ranked.fullFiscalYearFrom,
  fullFiscalYearTo: ranked.fullFiscalYearTo,
  officialSourceUrl: ranked.officialSourceUrl,
  officialSourceNote: ranked.officialSourceNote,
  excludedTransitionYears: ranked.excludedTransitionYears,
  rankingAmountStage: ranked.rankingAmountStage,
  rankings: [ranked],
}];

test("links the current term only through the approved official identifier", () => {
  assert.deepEqual(
    legislatureRankingForRepresentative(groups, "state", "921264", "2026-08-14"),
    { group: groups[0], row: ranked },
  );
  assert.equal(
    legislatureRankingForRepresentative(groups, "state", "outro-id", "2026-08-14"),
    null,
  );
});

test("does not turn a current federal profile into the author of a state amendment", () => {
  assert.equal(
    legislatureRankingForRepresentative(groups, "federal", "921264", "2026-08-14"),
    null,
  );
});

test("does not present a historical term as the representative current term", () => {
  assert.equal(
    legislatureRankingForRepresentative(groups, "state", "921264", "2028-01-01"),
    null,
  );
});
