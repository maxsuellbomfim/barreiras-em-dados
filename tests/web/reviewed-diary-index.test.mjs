import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const root = new URL('../../', import.meta.url);
test('índice revisado cobre 137 páginas uma vez sem deduplicar atas pelo título', async () => {
  const data = JSON.parse(await readFile(new URL('apps/web/app/diario/reviewed-4310.json', root), 'utf8'));
  assert.equal(data.edition, 4310);
  assert.equal(data.year, 2024);
  assert.equal(data.sha256, '424488a81d36041ea0588fc3846a3841812550b42627ef27a90cd076321faa0b');
  assert.equal(data.documents.length, 15);
  const pages = data.documents.flatMap(({ start, end }) => {
    assert.ok(Number.isInteger(start) && end >= start);
    return Array.from({length: end-start+1}, (_, i) => start+i);
  });
  assert.deepEqual(pages, Array.from({length:137}, (_, i) => i+1));
  assert.equal(new URL(data.url).hostname, 'www.barreiras.ba.gov.br');
});

test('índice só aparece no detalhe correspondente ao hash revisado, sem carregar PDF ou OCR', async () => {
  const component = await readFile(new URL('apps/web/app/diario/reviewed-diary-index.tsx', root), 'utf8');
  assert.match(component, /edition\.artifactSha256 !== review\.sha256/);
  assert.match(component, /edition\.edition !== review\.edition/);
  assert.match(component, /edition\.editionYear !== review\.year/);
  assert.match(component, /#page=/);
  assert.match(component, /<ol/);
  assert.doesNotMatch(component, /<iframe|<embed|fetch\(|use client/);
  const page = await readFile(new URL('apps/web/app/diario/[ano]/[edicao]/page.tsx', root), 'utf8');
  assert.match(page, /<ReviewedDiaryIndex edition=\{edition\}/);
});
