import assert from "node:assert/strict";
import test from "node:test";

import * as yearCoverage from
  "../../apps/web/lib/parliamentary-legislature-year-coverage.mjs";

const { parseParliamentaryLegislatureYearCoverageRows } = yearCoverage;

const observed = {
  sphere: "state",
  legislature_number: 20,
  fiscal_year: 2026,
  observation_status: "observed",
  contribution_count: 34,
  author_count: 7,
  primary_evidence_count: 34,
  methodology_version: "parliamentary-legislature-year-coverage/1.0.0",
};

test("preserves observed and not observed years without turning absence into zero", () => {
  const parsed = parseParliamentaryLegislatureYearCoverageRows([
    observed,
    {
      ...observed,
      fiscal_year: 2025,
      observation_status: "not_observed",
      contribution_count: 0,
      author_count: 0,
      primary_evidence_count: 0,
    },
  ]);
  assert.ok(parsed);
  assert.equal(parsed[0].observationStatus, "observed");
  assert.equal(parsed[1].observationStatus, "not_observed");
});

test("rejects incoherent status, impossible totals and duplicate years", () => {
  assert.equal(parseParliamentaryLegislatureYearCoverageRows([{
    ...observed,
    observation_status: "not_observed",
  }]), null);
  assert.equal(parseParliamentaryLegislatureYearCoverageRows([{
    ...observed,
    primary_evidence_count: 35,
  }]), null);
  assert.equal(parseParliamentaryLegislatureYearCoverageRows([
    observed,
    { ...observed },
  ]), null);
});

test("preserves the official collection reason when a ranking year has no rows", () => {
  const statuses = [
    "source_empty",
    "collection_incomplete",
    "source_blocked",
    "collected_no_record",
    "not_collected",
  ];
  const parsed = parseParliamentaryLegislatureYearCoverageRows(
    statuses.map((status, index) => ({
      ...observed,
      fiscal_year: 2020 + index,
      observation_status: status,
      contribution_count: 0,
      author_count: 0,
      primary_evidence_count: 0,
      methodology_version:
        "parliamentary-legislature-year-coverage/1.1.0",
    })),
  );

  assert.ok(parsed);
  assert.deepEqual(
    parsed.map((row) => row.observationStatus),
    statuses,
  );
});

test("explains each annual status without presenting a missing row as zero", () => {
  assert.equal(
    typeof yearCoverage.describeParliamentaryYearCoverageStatus,
    "function",
  );
  assert.deepEqual(
    [
      "observed",
      "source_empty",
      "collection_incomplete",
      "source_blocked",
      "collected_no_record",
      "not_collected",
      "not_observed",
    ].map((status) =>
      yearCoverage.describeParliamentaryYearCoverageStatus(status)
    ),
    [
      "dados encontrados",
      "fonte consultada sem registro individual",
      "coleta incompleta ou com falha",
      "fonte oficial bloqueada para este ano",
      "documento coletado, sem registro individual no ranking",
      "ano ainda não coletado",
      "registro individual ainda não observado",
    ],
  );
});
