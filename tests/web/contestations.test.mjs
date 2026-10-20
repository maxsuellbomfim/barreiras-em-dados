import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

import {
  normalizeProtocol,
  normalizeTargetPath,
  parseContestationRows,
} from "../../apps/web/lib/contestations.mjs";

test("página contestada aceita caminho ou endereço do próprio site", () => {
  assert.equal(normalizeTargetPath("/indicios"), "/indicios");
  assert.equal(
    normalizeTargetPath("https://barreiras-em-dados.vercel.app/financas/2026-08?x=1"),
    "/financas/2026-08?x=1",
  );
  assert.equal(normalizeTargetPath("https://outro-site.com/indicios"), null);
  assert.equal(normalizeTargetPath("indicios"), null);
  assert.equal(normalizeTargetPath("/com espaço"), null);
  assert.equal(normalizeTargetPath(`/${"a".repeat(300)}`), null);
});

test("protocolo tem formato fixo", () => {
  assert.equal(normalizeProtocol(" c-0aaea12762 "), "C-0AAEA12762");
  assert.equal(normalizeProtocol("C-123"), null);
});

test("consulta pública não expõe texto nem contato", () => {
  const found = parseContestationRows([{
    protocol: "C-0AAEA12762",
    target_path: "/indicios",
    status: "received",
    resolution_note: null,
    created_at: "2026-10-20T12:00:00+00:00",
    resolved_at: null,
  }]);
  assert.equal(found.state, "found");
  assert.equal("description" in found, false);
  assert.equal("contact" in found, false);
  assert.deepEqual(parseContestationRows([]), { state: "not_found" });
  assert.equal(parseContestationRows([{ protocol: "C-0AAEA12762", status: "x" }]), null);
});

test("nenhuma página manda contestar por issue do GitHub", async () => {
  const app = new URL("../../apps/web/app/", import.meta.url);
  const pages = (await readdir(app, { recursive: true })).filter((file) => file.endsWith(".tsx"));
  for (const page of pages) {
    const source = await readFile(new URL(page.replaceAll("\\", "/"), app), "utf8");
    assert.doesNotMatch(source, /github\.com\/[^"]*\/issues\/new/, page);
  }
});

test("formulário é anônimo, com campo-isca e aviso de privacidade", async () => {
  const form = await readFile(
    new URL("../../apps/web/app/contestar/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(form, /Não pedimos login nem identificação/);
  assert.match(form, /name="site"/);
  assert.match(form, /href="\/privacidade"/);
  const footer = await readFile(
    new URL("../../apps/web/app/site-chrome.tsx", import.meta.url),
    "utf8",
  );
  for (const href of ["/contestar", "/privacidade", "/termos"]) {
    assert.match(footer, new RegExp(`href="${href}"`));
  }
});
