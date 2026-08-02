import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const path = "fixtures/sources/municipal-source-catalog.json";
const catalog = JSON.parse(await readFile(path, "utf8"));

assert.equal(catalog.catalog_version, "1.0.0");
assert.equal(catalog.jurisdiction, "Barreiras-BA");
assert.ok(Array.isArray(catalog.sources) && catalog.sources.length >= 5);

const ids = new Set();
for (const source of catalog.sources) {
  assert.match(source.source_id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
  assert.ok(!ids.has(source.source_id), `${source.source_id}: id duplicado`);
  ids.add(source.source_id);
  assert.match(source.catalog_url, /^https:\/\//);
  assert.match(source.endpoint_url, /^https:\/\//);
  assert.match(source.observed_at, /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(Array.isArray(source.resources));
  assert.equal(new Set(source.resources).size, source.resources.length);
  if (source.rate_limit_per_minute !== undefined) {
    assert.ok(Number.isInteger(source.rate_limit_per_minute));
    assert.ok(source.rate_limit_per_minute > 0);
  }
}

const required = [
  "prefeitura-barreiras-transparencia",
  "camara-barreiras-transparencia",
  "pncp-barreiras",
  "siconfi-barreiras",
  "tcm-ba-barreiras",
  "tse-barreiras",
];
for (const sourceId of required) assert.ok(ids.has(sourceId), `${sourceId}: fonte ausente`);

process.stdout.write(`${catalog.sources.length} fontes municipais catalogadas e validas.\n`);
