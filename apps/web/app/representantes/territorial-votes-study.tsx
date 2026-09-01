"use client";

import { useMemo, useState } from "react";

import {
  classifyElectionOutcome,
  electionCycleLabel,
  electionPeriodLabel,
  latestElectionYear,
  outcomeLabel,
} from "../../lib/representative-election-context.mjs";
import type { ElectionOutcome } from "../../lib/representative-election-context.mjs";
import type { TseVote } from "../../lib/tse-votes";

const officeOrder = [
  "Prefeito",
  "Vereador",
  "Governador",
  "Senador",
  "Deputado Estadual",
  "Deputado Federal",
];

function formatNumber(value: number): string {
  return value.toLocaleString("pt-BR");
}

function officeSortIndex(office: string): number {
  const index = officeOrder.indexOf(office);
  return index === -1 ? officeOrder.length : index;
}

function displayName(vote: TseVote): string {
  return vote.ballotName ?? vote.displayName ?? "Candidatura sem nome informado";
}

const outcomeOptions: readonly Readonly<{
  value: ElectionOutcome | "todos";
  label: string;
}>[] = [
  { value: "todos", label: "Todas as situações" },
  { value: "elected", label: "Eleitos naquele pleito" },
  { value: "alternate", label: "Suplentes naquele pleito" },
  { value: "not_elected", label: "Não eleitos naquele pleito" },
  { value: "other", label: "Outras situações" },
  { value: "unknown", label: "Situação não informada" },
];

export default function TerritorialVotesStudy({
  votes,
}: Readonly<{ votes: readonly TseVote[] }>) {
  const years = useMemo(
    () => [...new Set(votes.map((vote) => vote.electionYear))].sort((a, b) => b - a),
    [votes],
  );
  const offices = useMemo(
    () =>
      [...new Set(votes.map((vote) => vote.office ?? "Cargo não informado"))].sort(
        (left, right) => officeSortIndex(left) - officeSortIndex(right) || left.localeCompare(right),
      ),
    [votes],
  );
  const [yearFilter, setYearFilter] = useState(() =>
    latestElectionYear(votes.map((vote) => vote.electionYear)),
  );
  const [officeFilter, setOfficeFilter] = useState("todos");
  const [turnFilter, setTurnFilter] = useState("todos");
  const [outcomeFilter, setOutcomeFilter] = useState<ElectionOutcome | "todos">("todos");
  const [search, setSearch] = useState("");
  const turns = useMemo(
    () => [...new Set(votes.map((vote) => vote.turnNumber))].sort((left, right) => left - right),
    [votes],
  );

  const filteredVotes = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");
    return votes.filter((vote) => {
      const matchesYear = yearFilter === "todos" || vote.electionYear === Number(yearFilter);
      const office = vote.office ?? "Cargo não informado";
      const matchesOffice = officeFilter === "todos" || office === officeFilter;
      const matchesTurn = turnFilter === "todos" || vote.turnNumber === Number(turnFilter);
      const matchesOutcome =
        outcomeFilter === "todos" || classifyElectionOutcome(vote.situation) === outcomeFilter;
      const matchesSearch =
        normalizedSearch.length === 0 ||
        [displayName(vote), vote.party, vote.candidateNumber, vote.candidateId]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase("pt-BR").includes(normalizedSearch));
      return matchesYear && matchesOffice && matchesTurn && matchesOutcome && matchesSearch;
    });
  }, [officeFilter, outcomeFilter, search, turnFilter, votes, yearFilter]);

  const summary = useMemo(() => {
    const groups = new Map<string, { year: number; office: string; turn: number; candidates: number; votes: number }>();
    for (const vote of filteredVotes) {
      const office = vote.office ?? "Cargo não informado";
      const key = `${vote.electionYear}-${office}-${vote.turnNumber}`;
      const current = groups.get(key) ?? { year: vote.electionYear, office, turn: vote.turnNumber, candidates: 0, votes: 0 };
      current.candidates += 1;
      current.votes += vote.votesInBarreiras;
      groups.set(key, current);
    }
    return [...groups.values()].sort(
      (left, right) => right.year - left.year || officeSortIndex(left.office) - officeSortIndex(right.office) || left.turn - right.turn,
    );
  }, [filteredVotes]);

  const totalVotes = useMemo(() => {
    if (turnFilter === "todos") return null;
    return filteredVotes.reduce((total, vote) => total + vote.votesInBarreiras, 0);
  }, [filteredVotes, turnFilter]);
  const electedCount = useMemo(
    () => filteredVotes.filter((vote) => classifyElectionOutcome(vote.situation) === "elected").length,
    [filteredVotes],
  );
  const topVotes = useMemo(
    () =>
      [...filteredVotes].sort(
        (left, right) =>
          right.votesInBarreiras - left.votesInBarreiras || displayName(left).localeCompare(displayName(right)),
      ),
    [filteredVotes],
  );
  const maxGroupVotes = Math.max(...summary.map((group) => group.votes), 1);

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
        <a className="territorial-study-source" href="https://dadosabertos.tse.jus.br/" target="_blank" rel="noreferrer">
          Fonte oficial: TSE ↗
        </a>
      </div>

      <div className="territorial-context-note" role="note">
        <strong>Candidatura não é mandato atual</strong>
        <p>
          Os mandatos atuais confirmados pela Prefeitura, Câmara Municipal,
          ALBA e Câmara dos Deputados ficam nas listas acima. Aqui, &ldquo;eleito&rdquo;,
          &ldquo;suplente&rdquo; ou &ldquo;não eleito&rdquo; descreve apenas o resultado daquela eleição.
        </p>
      </div>

      <div className="territorial-filters" aria-label="Filtros eleitorais">
        <label>
          <span>Ano da eleição</span>
          <select value={yearFilter} onChange={(event) => setYearFilter(event.target.value)}>
            <option value="todos">Todos os anos</option>
            {years.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </label>
        <label>
          <span>Cargo</span>
          <select value={officeFilter} onChange={(event) => setOfficeFilter(event.target.value)}>
            <option value="todos">Todos os cargos</option>
            {offices.map((office) => <option key={office} value={office}>{office}</option>)}
          </select>
        </label>
        <label>
          <span>Turno</span>
          <select value={turnFilter} onChange={(event) => setTurnFilter(event.target.value)}>
            <option value="todos">Todos (separados)</option>
            {turns.map((turn) => <option key={turn} value={turn}>{turn}º turno</option>)}
          </select>
        </label>
        <label>
          <span>Situação naquele pleito</span>
          <select
            value={outcomeFilter}
            onChange={(event) => setOutcomeFilter(event.target.value as ElectionOutcome | "todos")}
          >
            {outcomeOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="territorial-search">
          <span>Pesquisar candidatura</span>
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="nome, partido ou número" />
        </label>
      </div>

      <div className="territorial-kpis" aria-label="Resumo filtrado">
        <div><strong>{formatNumber(filteredVotes.length)}</strong><span>candidaturas no recorte</span></div>
        <div><strong>{formatNumber(electedCount)}</strong><span>eleitos naquele pleito</span></div>
        <div><strong>{totalVotes === null ? "—" : formatNumber(totalVotes)}</strong><span>{totalVotes === null ? "selecione um turno para somar votos" : "votos no turno selecionado"}</span></div>
      </div>

      {filteredVotes.length === 0 ? (
        <div className="collection-unavailable" role="status">
          <strong>Nenhum registro encontrado</strong>
          <p>Altere o ano, o cargo ou o termo de pesquisa.</p>
        </div>
      ) : (
        <>
          <section className="territorial-chart" aria-labelledby="territorial-chart-title">
            <div className="territorial-section-heading">
              <div><span className="eyebrow">Leitura rápida</span><h3 id="territorial-chart-title">Votos por eleição e cargo</h3></div>
              <span className="territorial-muted">Cálculo determinístico sobre o TSE</span>
            </div>
            <div className="territorial-bars">
              {summary.map((group) => (
                <div className="territorial-bar-row" key={`${group.year}-${group.office}-${group.turn}`}>
                  <div className="territorial-bar-label"><strong>{group.office} · {group.turn}º turno</strong><span>{group.year} · {formatNumber(group.candidates)} candidaturas</span></div>
                  <div className="territorial-bar-track" aria-label={`${formatNumber(group.votes)} votos`}><span style={{ width: `${Math.max(3, (group.votes / maxGroupVotes) * 100)}%` }} /></div>
                  <strong className="territorial-bar-value">{formatNumber(group.votes)}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="territorial-results" aria-labelledby="territorial-results-title">
            <div className="territorial-section-heading">
              <div><span className="eyebrow">Explorar registros</span><h3 id="territorial-results-title">Candidaturas mais votadas no recorte</h3></div>
              <span className="territorial-muted">{formatNumber(filteredVotes.length)} encontradas</span>
            </div>
            <div
              className="territorial-table-wrap"
              role="region"
              aria-labelledby="territorial-results-title"
              tabIndex={0}
            >
              <table className="territorial-table">
                <caption className="sr-only">Candidaturas filtradas por votação em Barreiras</caption>
                <thead><tr><th scope="col">Candidatura</th><th scope="col">Cargo disputado / eleição</th><th scope="col">Situação naquele pleito</th><th scope="col">Partido</th><th scope="col">Votos</th></tr></thead>
                <tbody>
                  {topVotes.slice(0, 50).map((vote) => {
                    const outcome = classifyElectionOutcome(vote.situation);
                    const office = vote.office ?? "Cargo não informado";
                    return (
                      <tr key={`${vote.electionYear}-${vote.candidateId}-${vote.turnNumber}`}>
                        <th scope="row">{displayName(vote)}<small>{vote.candidateNumber ? `nº ${vote.candidateNumber}` : "número não informado"}</small></th>
                        <td>{office}<small>{electionCycleLabel(vote.electionYear, office)} · {electionPeriodLabel(vote.electionYear, office)} · {vote.turnNumber}º turno</small></td>
                        <td><span className={`territorial-outcome territorial-outcome-${outcome}`}>{outcomeLabel(outcome)}</span><small>Fonte: {vote.situation ?? "não informado"}</small></td>
                        <td>{vote.party ?? "não informado"}</td>
                        <td className="territorial-table-number">{formatNumber(vote.votesInBarreiras)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {topVotes.length > 50 ? <p className="territorial-muted territorial-results-note">Mostrando as 50 maiores votações. Use os filtros e a busca para estudar os outros {formatNumber(topVotes.length)} registros.</p> : null}
          </section>
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
