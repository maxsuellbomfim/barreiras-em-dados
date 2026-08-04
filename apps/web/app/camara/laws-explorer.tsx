"use client";

import { useMemo, useState, type CSSProperties } from "react";

import type { CamaraLegislativeFilters, CamaraLegislativeItem } from "../../lib/camara-legislative";

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

export function CamaraLawsExplorer({ items, totalCount, page, pageSize, initialFilters }: Readonly<{
  items: readonly CamaraLegislativeItem[];
  totalCount: number;
  page: number;
  pageSize: number;
  initialFilters: CamaraLegislativeFilters;
}>) {
  const [query, setQuery] = useState(initialFilters.query ?? "");
  const [year, setYear] = useState(initialFilters.year?.toString() ?? "");
  const [kind, setKind] = useState<"all" | "lei" | "indicacao">(initialFilters.kind ?? "all");
  const [author, setAuthor] = useState(initialFilters.author ?? "");
  const filtered = items;
  const byAuthor = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of filtered) if (item.authorName) counts.set(item.authorName, (counts.get(item.authorName) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "pt-BR")).slice(0, 8);
  }, [filtered]);
  function filterQuery(targetPage?: number): string {
    const params = new URLSearchParams();
    const normalizedQuery = query.trim().slice(0, 200);
    const normalizedAuthor = author.trim().slice(0, 200);
    if (normalizedQuery) params.set("q", normalizedQuery);
    if (kind !== "all") params.set("kind", kind);
    if (/^\d{4}$/.test(year)) params.set("year", year);
    if (normalizedAuthor) params.set("author", normalizedAuthor);
    if (targetPage && targetPage > 1) params.set("page", String(targetPage));
    const queryString = params.toString();
    return queryString ? `/camara?${queryString}` : "/camara";
  }
  function authorQuery(name: string): string {
    const params = new URLSearchParams(filterQuery(1).split("?")[1] ?? "");
    params.set("author", name);
    return `/camara?${params.toString()}`;
  }
  function clearFilters() { window.location.assign("/camara"); }
  return (
    <div className="acts-explorer">
      <form className="acts-filters" aria-label="Filtrar atividade legislativa" onSubmit={(event) => { event.preventDefault(); window.location.assign(filterQuery(1)); }}>
        <label><span>Buscar em todo o acervo</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="título, ementa, protocolo ou autor" /></label>
        <label><span>Ano</span><input inputMode="numeric" pattern="\d{4}" maxLength={4} value={year} onChange={(event) => setYear(event.target.value.replace(/\D/g, "").slice(0, 4))} placeholder="todos" aria-label="Filtrar pelo ano" /></label>
        <label><span>Tipo</span><select value={kind} onChange={(event) => setKind(event.target.value as "all" | "lei" | "indicacao")}><option value="all">Leis e indicações</option><option value="lei">Leis</option><option value="indicacao">Indicações</option></select></label>
        <label><span>Autoria exata</span><input type="search" value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="nome como publicado pela fonte" /></label>
        <button type="submit" className="filter-clear">Aplicar filtros</button>
        <button type="button" className="filter-clear" onClick={clearFilters}>Limpar filtros</button>
      </form>
      <div className="acts-filter-summary" aria-live="polite"><strong>{filtered.length.toLocaleString("pt-BR")} nesta página · {totalCount.toLocaleString("pt-BR")} no recorte filtrado</strong><span>Os filtros são aplicados no servidor sobre todo o acervo. A página mostra até {pageSize} registros por vez.</span></div>
      {byAuthor.length > 0 ? <section className="legislative-author-summary" aria-label="Registros por autoria"><div><strong>Autoria publicada</strong><span>Amostra determinística desta página</span></div><div className="legislative-author-bars">{byAuthor.map(([name, count]) => <button type="button" key={name} onClick={() => { setAuthor(name); window.location.assign(authorQuery(name)); }} title={`Filtrar por ${name}`}><span>{name}</span><b style={{ "--bar-size": `${Math.max(8, Math.round((count / byAuthor[0][1]) * 100))}%` } as CSSProperties}>{count.toLocaleString("pt-BR")}</b></button>)}</div></section> : null}
      {filtered.length > 0 ? <div className="digest-grid">{filtered.map((item) => <LegislativeCard key={`${item.itemKind}-${item.itemId}`} item={item} />)}</div> : <div className="collection-unavailable" role="status"><div><strong>Nenhum registro neste recorte</strong><p>Altere os filtros ou limpe a busca para consultar todo o acervo.</p></div><button type="button" className="filter-clear" onClick={clearFilters}>Limpar filtros</button></div>}
      {totalCount > pageSize ? <nav className="legislative-pagination" aria-label="Paginação da atividade legislativa">{page > 1 ? <a className="filter-clear" href={filterQuery(page - 1)}>← Mais recentes</a> : <span />}{<span>Página {page} de {Math.ceil(totalCount / pageSize).toLocaleString("pt-BR")}</span>}{page * pageSize < totalCount ? <a className="filter-clear" href={filterQuery(page + 1)}>Registros anteriores →</a> : <span />}</nav> : null}
    </div>
  );
}
