import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const observations = [
  {
    path: "fixtures/sources/prefeitura-transparencia/catalog-observation.json",
    expectedCount: 51,
    expectedHost: "portaldatransparencia.barreiras.ba.gov.br",
  },
  {
    path: "fixtures/sources/camara-transparencia/catalog-observation.json",
    expectedCount: 28,
    expectedHost: "portaldatransparencia.cmbarreiras.ba.gov.br",
  },
];

for (const observation of observations) {
  const document = JSON.parse(await readFile(observation.path, "utf8"));

  assert.equal(document._fixture.contains_record_values, false);
  assert.equal(new URL(document.endpoint_url).protocol, "https:");
  assert.equal(new URL(document.endpoint_url).hostname, observation.expectedHost);
  assert.equal(document.resources.length, observation.expectedCount);
  assert.deepEqual(
    document.resources,
    [...new Set(document.resources)].sort(),
    `${observation.path}: recursos devem ser únicos e ordenados`,
  );
  assert.deepEqual(document.response_contract.success_root_fields, [
    "resource",
    "count",
    "data",
  ]);
  assert.equal(
    document.response_contract.pagination.count_semantics,
    "returned_rows",
  );
  assert.equal(document.response_contract.pagination.total_available, false);
}

console.log("2 catálogos sanitizados válidos: 79 recursos oficiais.");
