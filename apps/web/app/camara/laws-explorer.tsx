"use client";

import { useMemo, useState, type CSSProperties } from "react";

import type { CamaraLegislativeItem } from "../../lib/camara-legislative";

function formatDate(value: string | null): string {
  if (!value || Number.isNaN(Date.parse(value))) return "data não informada";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeZone: "America/Bahia" }).format(new Date(`${value.slice(0, 10)}T12:00:00Z`));
}

function itemLabel(item: CamaraLegislativeItem): string {
  return item.itemKind === "indicacao" ? "Indicação" : "Lei municipal";
}

function LegislativeCard({ item }: Readonly<{ item: CamaraLegislativeItem }>) {
  return (
    <article className="digest-card" aria-label={itemLabel(item)}>
      <div className="track-top"><span>{itemLabel(item)}</span><span className="track-status">{formatDate(item.publicationDate)}</span></div>
      <h2 className="procurement-object">{item.title || (item.itemKind === "indicacao" ? `Indicação ${item.itemId}` : `Lei ${item.itemId}`)}</h2>
      {item.summary ? <p>{item.summary}</p> : null}
      <dl className="procurement-values">
        <div><dt>Autoria informada pela Câmara</dt><dd>{item.authorName ?? "não informada"}</dd></div>
        <div><dt>{item.itemKind === "indicacao" ? "Protocolo" : "Identificador"}</dt><dd>{item.protocolNumber ?? item.itemId}</dd></div>
        {item.situation ? <div><dt>Situação na fonte</dt><dd>{item.situation}</dd></div> : null}
      </dl>
      {item.itemKind === "indicacao" ? <p className="act-review-mode">Indicação é uma proposição legislativa. Este registro não significa que a obra ou serviço foi executado.</p> : item.authorName ? <p className="act-review-mode">A autoria é exibida como publicada pela Câmara; não é uma avaliação do mandato.</p> : <p className="act-review-mode">A fonte não informou autoria individual neste registro. Nenhum vereador foi associado por semelhança de nome.</p>}
      <p className="act-evidence">{item.sourceUrl ? <a href={item.sourceUrl} target="_blank" rel="noreferrer">Ver documento oficial</a> : <span>Documento oficial não informado no registro</span>} · publicado em {formatDate(item.publicationDate)} · coletado em {formatDate(item.collectedAt)}</p>
    </article>
  );
}

export function CamaraLawsExplorer({ items, totalCount, page, pageSize }: Readonly<{
  items: readonly CamaraLegislativeItem[];
  totalCount: number;
  page: number;
  pageSize: number;
}>) {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("all");
  const [kind, setKind] = useState("all");
  const [author, setAuthor] = useState("all");
  const years = useMemo(() => Array.from(new Set(items.map((item) => item.referenceYear).filter((value): value is number => value !== null))).sort((a, b) => b - a), [items]);
  const authors = useMemo(() => Array.from(new Set(items.map((item) => item.authorName).filter((value): value is string => value !== null))).sort((a, b) => a.localeCompare(b, "pt-BR")), [items]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("pt-BR");
    return items.filter((item) => {
      if (kind !== "all" && item.itemKind !== kind) return false;
      if (year !== "all" && item.referenceYear !== Number(year)) return false;
      if (author !== "all" && item.authorName !== author) return false;
      return !needle || [item.itemId, item.protocolNumber, item.title, item.summary, item.authorName].filter(Boolean).join(" ").toLocaleLowerCase("pt-BR").includes(needle);
    });
  }, [author, items, kind, query, year]);
  const byAuthor = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of filtered) if (item.authorName) counts.set(item.authorName, (counts.get(item.authorName) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "pt-BR")).slice(0, 8);
  }, [filtered]);
  function clearFilters() { setQuery(""); setYear("all"); setKind("all"); setAuthor("all"); }
  return (
    <div className="acts-explorer">
      <form className="acts-filters" aria-label="Filtrar atividade legislativa">
        <label><span>Buscar nesta página</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="título, ementa, protocolo ou autor" /></label>
        <label><span>Ano</span><select value={year} onChange={(event) => setYear(event.target.value)}><option value="all">Todos</option>{years.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label><span>Tipo</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">Leis e indicações</option><option value="lei">Leis</option><option value="indicacao">Indicações</option></select></label>
        <label><span>Autoria publicada</span><select value={author} onChange={(event) => setAuthor(event.target.value)}><option value="all">Todas</option>{authors.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <button type="button" className="filter-clear" onClick={clearFilters}>Limpar filtros</button>
      </form>
      <div className="acts-filter-summary" aria-live="polite"><strong>{filtered.length.toLocaleString("pt-BR")} nesta página · {totalCount.toLocaleString("pt-BR")} no acervo</strong><span>Os filtros desta caixa atuam sobre a página atual.</span></div>
      {byAuthor.length > 0 ? <section className="legislative-author-summary" aria-label="Registros por autoria"><div><strong>Autoria publicada</strong><span>Contagem determinística na página atual</span></div><div className="legislative-author-bars">{byAuthor.map(([name, count]) => <button type="button" key={name} onClick={() => setAuthor(name)} title={`Filtrar por ${name}`}><span>{name}</span><b style={{ "--bar-size": `${Math.max(8, Math.round((count / byAuthor[0][1]) * 100))}%` } as CSSProperties}>{count.toLocaleString("pt-BR")}</b></button>)}</div></section> : null}
      {filtered.length > 0 ? <div className="digest-grid">{filtered.map((item) => <LegislativeCard key={`${item.itemKind}-${item.itemId}`} item={item} />)}</div> : <div className="collection-unavailable" role="status"><div><strong>Nenhum registro nesta página</strong><p>Use a navegação ou ajuste os filtros desta página.</p></div><button type="button" className="filter-clear" onClick={clearFilters}>Limpar filtros</button></div>}
      {totalCount > pageSize ? <nav className="legislative-pagination" aria-label="Paginação da atividade legislativa">{page > 1 ? <a className="filter-clear" href={`/camara?page=${page - 1}`}>← Mais recentes</a> : <span />}{<span>Página {page} de {Math.ceil(totalCount / pageSize).toLocaleString("pt-BR")}</span>}{page * pageSize < totalCount ? <a className="filter-clear" href={`/camara?page=${page + 1}`}>Registros anteriores →</a> : <span />}</nav> : null}
    </div>
  );
}
