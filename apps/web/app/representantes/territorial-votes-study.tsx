import {
  classifyElectionOutcome,
  electionCycleLabel,
  electionPeriodLabel,
  outcomeLabel,
} from "../../lib/representative-election-context.mjs";
import type {
  TseVote,
  TseVoteOutcome,
  TseVoteStudy,
  TseVoteStudyFilters,
} from "../../lib/tse-votes";

const outcomeOptions: readonly Readonly<{
  value: TseVoteOutcome | "todos";
  label: string;
}>[] = [
  { value: "todos", label: "Todas as situações" },
  { value: "elected", label: "Eleitos naquele pleito" },
  { value: "alternate", label: "Suplentes naquele pleito" },
  { value: "not_elected", label: "Não eleitos naquele pleito" },
  { value: "other", label: "Outras situações" },
  { value: "unknown", label: "Situação não informada" },
];

function formatNumber(value: number): string {
  return value.toLocaleString("pt-BR");
}

function displayName(vote: TseVote): string {
  return vote.ballotName ?? vote.displayName ?? "Candidatura sem nome informado";
}

function studyHref(
  filters: TseVoteStudyFilters,
  page: number,
): string {
  const params = new URLSearchParams();
  if (filters.allYears) params.set("ano", "todos");
  else if (filters.electionYear !== null) {
    params.set("ano", String(filters.electionYear));
  }
  if (filters.office) params.set("cargo", filters.office);
  if (filters.turn !== null) params.set("turno", String(filters.turn));
  if (filters.outcome) params.set("situacao", filters.outcome);
  if (filters.query) params.set("q", filters.query);
  if (page > 1) params.set("pagina", String(page));
  const query = params.toString();
  return `/representantes${query ? `?${query}` : ""}#vinculo`;
}

export default function TerritorialVotesStudy({
  study,
  filters,
}: Readonly<{
  study: TseVoteStudy;
  filters: TseVoteStudyFilters;
}>) {
  const {
    votes,
    totalCount,
    electedCount,
    votesTotal,
    groups,
    availableYears,
    availableOffices,
    availableTurns,
    effectiveYear,
    page,
    pageSize,
  } = study;
  const selectedYear = filters.allYears
    ? "todos"
    : String(filters.electionYear ?? effectiveYear ?? "todos");
  const maxGroupVotes = Math.max(...groups.map((group) => group.votes), 1);
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className="territorial-study">
      <div className="territorial-study-intro">
        <div>
          <span className="eyebrow">Vínculo territorial mensurável</span>
          <h2 id="candidates-title">Votos recebidos em Barreiras</h2>
          <p>
            Histórico de candidaturas que receberam votos no município,
            organizado pelo ano da eleição, cargo disputado e resultado
            publicado pelo TSE. Uma mesma pessoa pode aparecer em cargos ou
            pleitos diferentes; isso não informa, sozinho, qual cargo ocupa hoje.
          </p>
        </div>
        <a
          className="territorial-study-source"
          href="https://dadosabertos.tse.jus.br/"
          target="_blank"
          rel="noreferrer"
        >
          Fonte oficial: TSE ↗
        </a>
      </div>

      <div className="territorial-context-note" role="note">
        <strong>Candidatura não é mandato atual</strong>
        <p>
          Os mandatos atuais confirmados pela Prefeitura, Câmara Municipal,
          ALBA e Câmara dos Deputados ficam nas listas acima. Aqui,
          &ldquo;eleito&rdquo;, &ldquo;suplente&rdquo; ou &ldquo;não
          eleito&rdquo; descreve apenas o resultado daquela eleição.
        </p>
      </div>

      <form
        className="territorial-filters"
        aria-label="Filtros eleitorais"
        action="/representantes#vinculo"
        method="get"
      >
        <label>
          <span>Ano da eleição</span>
          <select name="ano" defaultValue={selectedYear}>
            <option value="todos">Todos os anos</option>
            {availableYears.map((year) => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Cargo</span>
          <select name="cargo" defaultValue={filters.office ?? "todos"}>
            <option value="todos">Todos os cargos</option>
            {availableOffices.map((office) => (
              <option key={office} value={office}>{office}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Turno</span>
          <select
            name="turno"
            defaultValue={filters.turn === null ? "todos" : String(filters.turn)}
          >
            <option value="todos">Todos (separados)</option>
            {availableTurns.map((turn) => (
              <option key={turn} value={turn}>{turn}º turno</option>
            ))}
          </select>
        </label>
        <label>
          <span>Situação naquele pleito</span>
          <select name="situacao" defaultValue={filters.outcome ?? "todos"}>
            {outcomeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="territorial-search">
          <span>Pesquisar candidatura</span>
          <input
            type="search"
            name="q"
            maxLength={100}
            defaultValue={filters.query ?? ""}
            placeholder="nome, partido ou número"
          />
        </label>
        <button type="submit" className="filter-clear">Aplicar filtros</button>
        <a className="filter-clear" href="/representantes#vinculo">
          Limpar filtros
        </a>
      </form>

      <div className="acts-filter-summary" aria-live="polite">
        <strong>
          {formatNumber(votes.length)} nesta página · {formatNumber(totalCount)} no recorte filtrado
        </strong>
        <span>
          Os filtros são aplicados no servidor sobre todo o acervo. A página
          mostra até {pageSize} registros por vez.
        </span>
      </div>

      <div className="territorial-kpis" aria-label="Resumo filtrado">
        <div>
          <strong>{formatNumber(totalCount)}</strong>
          <span>candidaturas no recorte</span>
        </div>
        <div>
          <strong>{formatNumber(electedCount)}</strong>
          <span>eleitos naquele pleito</span>
        </div>
        <div>
          <strong>{votesTotal === null ? "—" : formatNumber(votesTotal)}</strong>
          <span>
            {votesTotal === null
              ? "selecione um turno para somar votos"
              : "votos no turno selecionado"}
          </span>
        </div>
      </div>

      {totalCount === 0 ? (
        <div className="collection-unavailable" role="status">
          <strong>Nenhum registro encontrado</strong>
          <p>Altere o ano, o cargo, a situação ou o termo de pesquisa.</p>
        </div>
      ) : (
        <>
          <section className="territorial-chart" aria-labelledby="territorial-chart-title">
            <div className="territorial-section-heading">
              <div>
                <span className="eyebrow">Leitura rápida</span>
                <h3 id="territorial-chart-title">Votos por eleição e cargo</h3>
              </div>
              <span className="territorial-muted">
                Cálculo determinístico sobre todo o recorte do TSE
              </span>
            </div>
            <div className="territorial-bars">
              {groups.map((group) => (
                <div
                  className="territorial-bar-row"
                  key={`${group.year}-${group.office}-${group.turn}`}
                >
                  <div className="territorial-bar-label">
                    <strong>{group.office} · {group.turn}º turno</strong>
                    <span>{group.year} · {formatNumber(group.candidates)} candidaturas</span>
                  </div>
                  <div
                    className="territorial-bar-track"
                    aria-label={`${formatNumber(group.votes)} votos`}
                  >
                    <span
                      style={{
                        width: `${Math.max(3, (group.votes / maxGroupVotes) * 100)}%`,
                      }}
                    />
                  </div>
                  <strong className="territorial-bar-value">
                    {formatNumber(group.votes)}
                  </strong>
                </div>
              ))}
            </div>
          </section>

          <section className="territorial-results" aria-labelledby="territorial-results-title">
            <div className="territorial-section-heading">
              <div>
                <span className="eyebrow">Explorar registros</span>
                <h3 id="territorial-results-title">Candidaturas mais votadas no recorte</h3>
              </div>
              <span className="territorial-muted">
                {formatNumber(totalCount)} encontradas
              </span>
            </div>
            <div
              className="territorial-table-wrap"
              role="region"
              aria-labelledby="territorial-results-title"
              tabIndex={0}
            >
              <table className="territorial-table">
                <caption className="sr-only">
                  Candidaturas filtradas por votação em Barreiras
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Candidatura</th>
                    <th scope="col">Cargo disputado / eleição</th>
                    <th scope="col">Situação naquele pleito</th>
                    <th scope="col">Partido</th>
                    <th scope="col">Votos</th>
                  </tr>
                </thead>
                <tbody>
                  {votes.map((vote) => {
                    const outcome = classifyElectionOutcome(vote.situation);
                    const office = vote.office ?? "Cargo não informado";
                    return (
                      <tr key={`${vote.electionYear}-${vote.candidateId}-${vote.turnNumber}`}>
                        <th scope="row">
                          {displayName(vote)}
                          <small>
                            {vote.candidateNumber
                              ? `nº ${vote.candidateNumber}`
                              : "número não informado"}
                          </small>
                        </th>
                        <td>
                          {office}
                          <small>
                            {electionCycleLabel(vote.electionYear, office)} · {" "}
                            {electionPeriodLabel(vote.electionYear, office)} · {" "}
                            {vote.turnNumber}º turno
                          </small>
                        </td>
                        <td>
                          <span className={`territorial-outcome territorial-outcome-${outcome}`}>
                            {outcomeLabel(outcome)}
                          </span>
                          <small>Fonte: {vote.situation ?? "não informado"}</small>
                        </td>
                        <td>{vote.party ?? "não informado"}</td>
                        <td className="territorial-table-number">
                          {formatNumber(vote.votesInBarreiras)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {pageCount > 1 ? (
            <nav className="legislative-pagination" aria-label="Paginação eleitoral">
              {page > 1 ? (
                <a className="filter-clear" href={studyHref(filters, page - 1)}>
                  ← Votações anteriores
                </a>
              ) : <span />}
              <span>Página {page} de {formatNumber(pageCount)}</span>
              {page < pageCount ? (
                <a className="filter-clear" href={studyHref(filters, page + 1)}>
                  Mais candidaturas →
                </a>
              ) : <span />}
            </nav>
          ) : null}
        </>
      )}

      <details className="territorial-methodology">
        <summary>Como interpretar este vínculo</summary>
        <p>
          O vínculo é territorial: o TSE informa a votação nominal agregada no
          município. O cargo exibido é o disputado naquele pleito, não uma
          declaração de cargo atual. A plataforma não presume que todo candidato
          votado em Barreiras represente a cidade. A associação com um perfil
          atual ocorre separadamente e somente por crosswalk revisado com
          identificadores oficiais — nunca apenas por semelhança de nome.
        </p>
      </details>
    </div>
  );
}
