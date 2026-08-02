"use client";

import { useMemo, useState } from "react";

import type { CamaraLaw } from "../../lib/camara-laws";

function LawCard({ law }: Readonly<{ law: CamaraLaw }>) {
  return (
    <article className="digest-card" aria-label="Lei municipal">
      <div className="track-top">
        <span>{law.lawType ?? "Lei municipal"}</span>
        <span className="track-status">
          {law.referenceYear ?? law.publicationDate ?? "ano não informado"}
        </span>
      </div>
      <h2 className="procurement-object">
        {law.title ?? `Registro legislativo ${law.lawId}`}
      </h2>
      {law.summary ? <p>{law.summary}</p> : null}
      <dl className="procurement-values">
        <div>
          <dt>Identificador na Câmara</dt>
          <dd>{law.lawId}</dd>
        </div>
        <div>
          <dt>Data publicada</dt>
          <dd>{law.publicationDate ?? "não informado"}</dd>
        </div>
        <div>
          <dt>Status informado pela fonte</dt>
          <dd>
            {law.active === null ? "não informado" : law.active ? "ativo" : "inativo"}
          </dd>
        </div>
      </dl>
      <p className="act-review-mode">
        A API consultada não atribuiu autoria individual neste registro. Não
        inferimos vereador, partido ou avaliação a partir da ementa.
      </p>
      <p className="act-evidence">
        {law.sourceUrl ? (
          <a href={law.sourceUrl} target="_blank" rel="noreferrer">
            Ver arquivo oficial
          </a>
        ) : (
          <span>Arquivo oficial não informado no registro</span>
        )}{" "}
        · coletado em {new Date(law.collectedAt).toLocaleDateString("pt-BR")}
      </p>
    </article>
  );
}

export function CamaraLawsExplorer({
  laws,
}: Readonly<{ laws: readonly CamaraLaw[] }>) {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("all");
  const [type, setType] = useState("all");

  const years = useMemo(
    () =>
      Array.from(
        new Set(
          laws
            .map((law) => law.referenceYear)
            .filter((value): value is number => value !== null),
        ),
      ).sort((a, b) => b - a),
    [laws],
  );
  const types = useMemo(
    () =>
      Array.from(
        new Set(
          laws
            .map((law) => law.lawType)
            .filter((value): value is string => value !== null),
        ),
      ).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [laws],
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    return laws.filter((law) => {
      if (
        normalizedQuery &&
        ![
          law.lawId,
          law.title,
          law.summary,
          law.lawType,
        ]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase("pt-BR")
          .includes(normalizedQuery)
      ) {
        return false;
      }
      if (year !== "all" && law.referenceYear !== Number(year)) return false;
      if (type !== "all" && law.lawType !== type) return false;
      return true;
    });
  }, [laws, query, type, year]);

  function clearFilters() {
    setQuery("");
    setYear("all");
    setType("all");
  }

  return (
    <div className="acts-explorer">
      <form className="acts-filters" aria-label="Filtrar leis municipais">
        <label>
          <span>Buscar</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="título, ementa ou identificador"
          />
        </label>
        <label>
          <span>Ano</span>
          <select value={year} onChange={(event) => setYear(event.target.value)}>
            <option value="all">Todos</option>
            {years.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          <span>Tipo</span>
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="all">Todos</option>
            {types.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <button type="button" className="filter-clear" onClick={clearFilters}>Limpar filtros</button>
      </form>
      <div className="acts-filter-summary" aria-live="polite">
        <strong>{filtered.length.toLocaleString("pt-BR")} de {laws.length.toLocaleString("pt-BR")} registros</strong>
        <span>Leis preservadas da API oficial da Câmara Municipal.</span>
      </div>
      {filtered.length > 0 ? (
        <div className="digest-grid">
          {filtered.map((law) => <LawCard key={law.lawId} law={law} />)}
        </div>
      ) : (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Nenhuma lei corresponde aos filtros</strong>
            <p>Ajuste a busca ou limpe os filtros.</p>
          </div>
          <button type="button" className="filter-clear" onClick={clearFilters}>Mostrar todos</button>
        </div>
      )}
    </div>
  );
}
