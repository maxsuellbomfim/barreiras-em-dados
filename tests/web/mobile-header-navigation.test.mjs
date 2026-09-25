import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

const app = new URL("../../apps/web/app/", import.meta.url);
const styles = await readFile(new URL("globals.css", app), "utf8");
const nav = await readFile(new URL("site-nav.tsx", app), "utf8");
const layout = await readFile(new URL("layout.tsx", app), "utf8");

test("cabeçalho e rodapé únicos vêm do layout, não de cada página", async () => {
  assert.match(layout, /<SiteHeader \/>[\s\S]*\{children\}[\s\S]*<SiteFooter \/>/);
  const pages = (await readdir(app, { recursive: true })).filter((file) =>
    file.endsWith("page.tsx"),
  );
  for (const page of pages) {
    const source = await readFile(new URL(page.replaceAll("\\", "/"), app), "utf8");
    assert.doesNotMatch(source, /className="site-header"/, page);
    assert.doesNotMatch(source, /<footer>/, page);
  }
});

test("menu tem as mesmas seções, com a página atual marcada", () => {
  for (const [href, label] of [
    ["/financas", "Dinheiro público"],
    ["/licitacoes", "Compras"],
    ["/representantes", "Quem decide"],
    ["/diario", "Diário Oficial"],
    ["/atos", "Nomeações"],
    ["/camara", "Câmara"],
    ["/recursos", "Emendas"],
  ]) {
    assert.match(nav, new RegExp(`href: "${href}", label: "${label}"`));
  }
  assert.match(nav, /aria-current=\{isCurrent\(pathname, section\.href\) \? "page" : undefined\}/);
});

test("no celular, o menu abre por botão com alvos de toque de 48px", () => {
  assert.match(
    styles,
    /@media \(max-width: 720px\)[\s\S]*?\.nav-links\s*\{\s*display:\s*none;\s*\}[\s\S]*?\.nav-menu\s*\{\s*display:\s*block;\s*\}/,
  );
  assert.match(styles, /\.nav-menu-panel a\s*\{[^}]*min-height:\s*3rem;/);
  assert.match(nav, /<details className="nav-menu">/);
});
