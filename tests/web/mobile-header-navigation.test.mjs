import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const styles = await readFile(
  new URL("../../apps/web/app/globals.css", import.meta.url),
  "utf8",
);

test("cabeçalho móvel reserva uma linha legível para a navegação pública", () => {
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.nav-shell\s*\{[^}]*flex-direction:\s*column;[^}]*align-items:\s*stretch;[^}]*gap:\s*0\.45rem;/,
  );
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.nav-links\s*\{[^}]*width:\s*100%;[^}]*margin-left:\s*0;/,
  );
});

test("navegação móvel continua rolável, sem ocultar destinos", () => {
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.nav-links\s*\{[^}]*overflow-x:\s*auto;[^}]*flex-wrap:\s*nowrap;/,
  );
});
