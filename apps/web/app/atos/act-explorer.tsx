"use client";

import { useMemo, useState } from "react";

import type { ApprovedGazetteAct } from "../../lib/approved-acts";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "long",
  year: "numeric",
  timeZone: "America/Bahia",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

function inferredPersonName(act: ApprovedGazetteAct): string | null {
  if (act.personName) return act.personName;
  const summary = act.assistedSummary?.trim();
  if (!summary) return null;
  const match = summary.match(
    /\b(?:designa|designou|nomeia|nomeou|exonera|exonerou|dispensa|dispensou)\s+(?:o|a|servidor|servidora|funcionário|funcionária)?\s*([A-ZÁÉÍÓÚÃÕÇ][\p{L}'-]+(?:\s+[A-ZÁÉÍÓÚÃÕÇ][\p{L}'-]+){1,8})/u,
  );
  return match?.[1]?.replace(/[.,;:]$/, "") ?? null;
}

function ActCard({ act }: Readonly<{ act: ApprovedGazetteAct }>) {
  const headline = inferredPersonName(act);
  const inferred = !act.personName && headline !== null;
  return (
    <article className="track-card" aria-label="Ato oficial revisado">
      <div className="track-top">
        <span>{act.actType === "nomeacao" ? "Nomeação" : "Exoneração"}</span>
        <span className="track-status">
          {act.gazetteDate
            ? `Ato de ${formatDate(act.gazetteDate)}`
            : "Data do ato não informada"}
        </span>
      </div>
      <h2>{headline ?? "Pessoa não identificada no ato"}</h2>
      {inferred ? (
        <p className="act-inference-note">
          Nome recuperado do resumo assistido; confira o trecho oficial.
        </p>
      ) : null}
      <p>
        {[
          act.positionTitle,
          act.positionSymbol ? `símbolo ${act.positionSymbol}` : null,
          act.organization,
        ]
          .filter(Boolean)
          .join(" · ") ||
          "Detalhes do cargo disponíveis no trecho do documento oficial."}
      </p>
      {act.assistedSummary ? (
        <p className="act-summary">
          <strong>Em palavras simples:</strong> {act.assistedSummary}
          <span className="act-summary-label">
            Resumo gerado com IA e conferido na revisão humana.
          </span>
        </p>
      ) : null}
      {act.excerpt ? (
        <details>
          <summary>Trecho do documento oficial</summary>
          <pre className="act-excerpt">{act.excerpt}</pre>
        </details>
      ) : null}
      <p className="act-evidence">
        {act.gazetteUrl ? (
          <a href={act.gazetteUrl} target="_blank" rel="noreferrer">
            Ver o documento oficial (PDF)
          </a>
        ) : (
          <span>Documento preservado no acervo verificável</span>
        )}{" "}
        · hash {act.artifactSha256.slice(0, 12)}… · publicado em{" "}
        {dateTimeFormatter.format(new Date(act.approvedAt))}
      </p>
      <p className="act-review-mode">
        {act.reviewMode === "human"
          ? "Revisado por uma pessoa antes de publicar."
          : "Publicação automática: dados conferidos por código contra o documento oficial. Sujeita a correção — e toda correção fica registrada."}
      </p>
    </article>
  );
}

function searchableText(act: ApprovedGazetteAct) {
  return [
    act.personName,
    act.positionTitle,
    act.positionSymbol,
    act.organization,
    act.excerpt,
    act.assistedSummary,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("pt-BR");
}

export function ActExplorer({
  acts,
}: Readonly<{ acts: readonly ApprovedGazetteAct[] }>) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [organization, setOrganization] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const organizations = useMemo(
    () =>
      Array.from(
        new Set(
          acts
            .map((act) => act.organization)
            .filter((value): value is string => value !== null),
        ),
      ).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [acts],
  );

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    return acts.filter((act) => {
      if (normalizedQuery && !searchableText(act).includes(normalizedQuery)) {
        return false;
      }
      if (type !== "all" && act.actType !== type) {
        return false;
      }
      if (organization !== "all" && act.organization !== organization) {
        return false;
      }
      if (from && (!act.gazetteDate || act.gazetteDate < from)) {
        return false;
      }
      if (to && (!act.gazetteDate || act.gazetteDate > to)) {
        return false;
      }
      return true;
    });
  }, [acts, from, organization, query, to, type]);

  function clearFilters() {
    setQuery("");
    setType("all");
    setOrganization("all");
    setFrom("");
    setTo("");
  }

  return (
    <div className="acts-explorer">
      <form className="acts-filters" aria-label="Filtrar atos publicados">
        <label>
          <span>Buscar</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="nome, cargo ou secretaria"
          />
        </label>
        <label>
          <span>Tipo de ato</span>
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="all">Nomeações e exonerações</option>
            <option value="nomeacao">Nomeações</option>
            <option value="exoneracao">Exonerações</option>
          </select>
        </label>
        <label>
          <span>Órgão ou secretaria</span>
          <select
            value={organization}
            onChange={(event) => setOrganization(event.target.value)}
          >
            <option value="all">Todos</option>
            {organizations.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>De</span>
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label>
          <span>Até</span>
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
        <button type="button" className="filter-clear" onClick={clearFilters}>
          Limpar filtros
        </button>
      </form>

      <div className="acts-filter-summary" aria-live="polite">
        <strong>
          {filtered.length.toLocaleString("pt-BR")} de {acts.length.toLocaleString("pt-BR")} atos
        </strong>
        <span>Filtros aplicados somente sobre registros já aprovados e publicados.</span>
      </div>

      {filtered.length > 0 ? (
        <div className="track-grid">
          {filtered.map((act) => (
            <ActCard key={act.actId} act={act} />
          ))}
        </div>
      ) : (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Nenhum ato corresponde aos filtros</strong>
            <p>
              Ajuste os campos ou limpe os filtros. Isso não significa ausência
              de atos na fonte oficial.
            </p>
          </div>
          <button type="button" className="filter-clear" onClick={clearFilters}>
            Mostrar todos
          </button>
        </div>
      )}
    </div>
  );
}
