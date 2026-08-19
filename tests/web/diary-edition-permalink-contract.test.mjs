import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260819070000_integral_gazette_edition_permalink.sql",
    import.meta.url,
  ),
  "utf8",
);
const route = await readFile(
  new URL(
    "../../apps/web/app/diario/[ano]/[edicao]/page.tsx",
    import.meta.url,
  ),
  "utf8",
);
const lib = await readFile(
  new URL(
    "../../apps/web/lib/integral-gazette-documents.ts",
    import.meta.url,
  ),
  "utf8",
);
const explorer = await readFile(
  new URL(
    "../../apps/web/app/diario/integral-gazette-explorer.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("a RPC da edição única mantém a regra de um lote por edição", () => {
  assert.match(migration, /get_integral_gazette_edition/);
  assert.match(
    migration,
    /distinct on \(version\.edition_year, version\.edition\)/,
  );
  assert.match(
    migration,
    /gazette-direct-edition/,
    "a coleta direta continua preferida sobre o Querido Diário",
  );
  assert.match(migration, /'validated', 'edition_fallback'/);
  assert.match(migration, /grant execute[\s\S]*to anon, authenticated/);
});

test("a rota valida parâmetros e distingue 404 de indisponibilidade", () => {
  assert.match(route, /notFound\(\)/);
  assert.match(
    route,
    /result\.state === "available" && result\.edition === null\) notFound/,
    "edição inexistente é 404",
  );
  assert.match(
    route,
    /falha de consulta, não a inexistência da\s+edição/,
    "falha de fonte nunca vira 404",
  );
  assert.match(route, /String\(editionYear\) !== ano\.trim\(\)/);
  assert.match(route, /ShareLink/);
  assert.match(route, /canonical: `\/diario\/\$\{parsed\.editionYear\}\/\$\{parsed\.edition\}`/);
});

test("o parser da edição única reutiliza o contrato literal existente", () => {
  assert.match(lib, /getIntegralGazetteEdition\(/);
  assert.match(
    lib,
    /if \(payload\.length === 0\) return \{ state: "available", edition: null \}/,
    "zero linhas é ausência declarada, não indisponibilidade",
  );
  assert.match(lib, /parseIntegralGazetteEdition\(payload\[0\]\)/);
});

test("cada edição do acervo aponta para seu endereço permanente", () => {
  assert.match(
    explorer,
    /href=\{`\/diario\/\$\{edition\.editionYear\}\/\$\{edition\.edition\}`\}/,
  );
});
