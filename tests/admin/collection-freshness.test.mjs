import assert from "node:assert/strict";
import test from "node:test";

import {
  formatFreshnessPolicy,
  formatFreshnessStatus,
  freshnessRequiresAttention,
} from "../../apps/admin/app/collection-freshness.mjs";

test("traduz fonte dentro do prazo sem confundir com cobertura", () => {
  const item = {
    freshness_status: "current",
    freshness_expected_hours: 24,
    freshness_grace_hours: 24,
    freshness_due_at: "2026-08-15T10:00:00Z",
    freshness_overdue_hours: 0,
  };

  assert.equal(formatFreshnessStatus(item), "Atualização dentro do prazo");
  assert.equal(
    formatFreshnessPolicy(item),
    "Até 48 horas entre atualizações válidas",
  );
  assert.equal(freshnessRequiresAttention(item), false);
});

test("explica atraso pela atualização válida e não pela tentativa falha", () => {
  const item = {
    freshness_status: "overdue",
    freshness_expected_hours: 168,
    freshness_grace_hours: 24,
    freshness_due_at: "2026-08-12T10:00:00Z",
    freshness_overdue_hours: 37,
  };

  assert.equal(
    formatFreshnessStatus(item),
    "Atualização atrasada há cerca de 37 horas",
  );
  assert.equal(freshnessRequiresAttention(item), true);
});

test("distingue fonte programada nunca concluída de fonte por publicação", () => {
  const neverUpdated = {
    freshness_status: "never_updated",
    freshness_expected_hours: 24,
    freshness_grace_hours: 24,
    freshness_due_at: null,
    freshness_overdue_hours: null,
  };
  const publicationDriven = {
    freshness_status: "not_monitored",
    freshness_expected_hours: null,
    freshness_grace_hours: 0,
    freshness_due_at: null,
    freshness_overdue_hours: null,
  };

  assert.equal(
    formatFreshnessStatus(neverUpdated),
    "Nenhuma atualização válida registrada",
  );
  assert.equal(
    formatFreshnessStatus(publicationDriven),
    "Sem prazo contínuo definido",
  );
  assert.equal(freshnessRequiresAttention(neverUpdated), true);
  assert.equal(freshnessRequiresAttention(publicationDriven), false);
});
