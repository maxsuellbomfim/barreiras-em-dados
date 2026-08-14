import type { Metadata } from "next";

import {
  getMunicipalCouncillors,
  type Councillor,
} from "../../lib/councillors";
import {
  getFederalRepresentatives,
  type FederalRepresentative,
} from "../../lib/representatives";
import {
  getStateRepresentatives,
  type StateRepresentative,
} from "../../lib/state-representatives";
import { getTseBarreirasVotes, type TseVote } from "../../lib/tse-votes";
import {
  getRepresentativeVotes,
  votesForRepresentative,
  type RepresentativeVote,
} from "../../lib/representative-votes";
import TerritorialVotesStudy from "./territorial-votes-study";
import RepresentativeTrajectory from "./representative-trajectory";
import {
  getExecutiveProfiles,
  type ExecutiveProfile,
} from "../../lib/executive-profiles";
import {
  getPublicParliamentaryTransferRankings,
  getPublicStateLoaRepresentativeContributions,
  parliamentaryTransferAuthorAnchor,
  transferSummaryForRepresentative,
  type ParliamentaryTransferRanking,
  type StateLoaRepresentativeContribution,
} from "../../lib/parliamentary-transfers";
import { stateLoaContributionsForRepresentative } from
  "../../lib/state-loa-representative-contributions.mjs";
import { formatBrlDecimal } from "../../lib/revenues";
import { getPublicParliamentaryLegislatureRankings } from
  "../../lib/legislature-transfer-rankings";
import LegislatureTransferRankings from "./legislature-transfer-rankings";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Quem representa Barreiras",
  description:
    "Deputados, vereadores e secretários com registro público e vínculo " +
    "territorial explícito — cada informação com fonte verificável.",
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function countLabel(count: number | null): string {
  return count === null ? "—" : count.toLocaleString("pt-BR");
}

function RepresentativeTransferSummary({
  summary,
}: Readonly<{ summary: ParliamentaryTransferRanking | null }>) {
  if (!summary) return null;
  return (
    <div className="person-vote-summary person-transfer-summary" aria-label="Emendas para Barreiras">
      <div className="person-vote-summary-heading">
        <strong>Recursos destinados a Barreiras</strong>
        <span className="person-vote-summary-badge">autoria confirmada</span>
      </div>
      <ul>
        <li>
          <span>Valor destinado</span>
          <strong>{formatBrlDecimal(summary.destinationAmount)}</strong>
        </li>
        <li>
          <span>Pagamento confirmado</span>
          <strong>
            {summary.paidAmount === null
              ? "não encontrado na fonte"
              : formatBrlDecimal(summary.paidAmount)}
          </strong>
        </li>
        <li>
          <span>Emendas no recorte</span>
          <strong>{summary.amendmentCount.toLocaleString("pt-BR")}</strong>
        </li>
      </ul>
      <p>Valores oficiais por estágio; recurso destinado não significa recurso pago.</p>
      <a href={`/recursos#${parliamentaryTransferAuthorAnchor(summary.authorKey)}`}>
        Ver emendas e documentos →
      </a>
    </div>
  );
}

function StateLoaContributionTimeline({
  rows,
}: Readonly<{ rows: readonly StateLoaRepresentativeContribution[] }>) {
  if (rows.length === 0) return null;
  return (
    <details className="person-state-loa-timeline">
      <summary>
        <span>
          <strong>Emendas estaduais para Barreiras</strong>
          <small>autoria ligada por identificadores oficiais</small>
        </span>
        <span>{rows.length.toLocaleString("pt-BR")} ano(s)</span>
      </summary>
      <div className="person-state-loa-timeline-body">
        <p>
          Autorização na LOA não significa pagamento. Os valores de execução
          aparecem somente quando a emenda possui ligação oficial única com o
          arquivo financeiro estadual.
        </p>
        {rows.map((row) => (
          <section
            className="person-state-loa-year"
            key={`${row.authorKey}:${row.fiscalYear}`}
          >
            <div className="person-state-loa-year-heading">
              <h3>{row.fiscalYear}</h3>
              <span>{row.amendmentCount.toLocaleString("pt-BR")} emenda(s)</span>
            </div>
            <dl>
              <div>
                <dt>Autorizado na LOA</dt>
                <dd>{formatBrlDecimal(row.authorizedAmount)}</dd>
              </div>
              {row.matchedAmendmentCount > 0 ? (
                <>
                  <div>
                    <dt>Emendas com ligação única</dt>
                    <dd>
                      {row.matchedAmendmentCount.toLocaleString("pt-BR")} de{" "}
                      {row.amendmentCount.toLocaleString("pt-BR")}
                    </dd>
                  </div>
                  <div>
                    <dt>Autorizado no subconjunto conciliado</dt>
                    <dd>{formatBrlDecimal(row.matchedAuthorizedAmount!)}</dd>
                  </div>
                  <div>
                    <dt>Empenhado no subconjunto conciliado</dt>
                    <dd>{formatBrlDecimal(row.committedAmount!)}</dd>
                  </div>
                  <div>
                    <dt>Liquidação no subconjunto conciliado</dt>
                    <dd>{formatBrlDecimal(row.liquidatedAmount!)}</dd>
                  </div>
                  <div>
                    <dt>Pago no subconjunto conciliado</dt>
                    <dd>{formatBrlDecimal(row.paidAmount!)}</dd>
                  </div>
                </>
              ) : null}
            </dl>
            {row.matchedAmendmentCount === 0 ? (
              <p className="person-state-loa-limit">
                Execução financeira não atribuída com segurança neste exercício;
                isso não significa valor zero nem ausência de execução.
              </p>
            ) : row.blockedAmendmentCount > 0 ? (
              <p className="person-state-loa-limit">
                {row.blockedAmendmentCount.toLocaleString("pt-BR")} emenda(s) sem
                ligação financeira única ficaram fora dos valores de execução.
              </p>
            ) : null}
            <a
              href={`/recursos?origem=estadual&ano=${row.fiscalYear}#${parliamentaryTransferAuthorAnchor(row.authorKey)}`}
            >
              Conferir emendas, objetos e documentos de {row.fiscalYear} →
            </a>
          </section>
        ))}
      </div>
    </details>
  );
}

function RepresentativeCard({
  person,
  voteLinks,
  transferSummary,
  stateLoaContributions,
}: Readonly<{
  person: FederalRepresentative;
  voteLinks: readonly RepresentativeVote[];
  transferSummary: ParliamentaryTransferRanking | null;
  stateLoaContributions: readonly StateLoaRepresentativeContribution[];
}>) {
  const camaraUrl = `https://www.camara.leg.br/deputados/${person.externalId}`;
  return (
    <article
      className="person-card"
      id={`federal-${person.externalId}`}
      aria-label="Representante"
    >
      <div className="person-head">
        {person.photoUrl ? (
          // Foto oficial publicada pela própria Câmara.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="person-photo"
            src={person.photoUrl}
            alt=""
            width={72}
            height={96}
            loading="lazy"
          />
        ) : (
          <span className="person-photo person-photo-empty" aria-hidden="true" />
        )}
        <div>
          <h2>{person.displayName}</h2>
          <p className="person-role">
            Deputado(a) federal
            {person.party ? ` · ${person.party}` : ""}
            {person.stateCode ? `/${person.stateCode}` : ""}
          </p>
          {person.mandateStatus ? (
            <span
              className={
                person.mandateStatus.toLowerCase().includes("exerc")
                  ? "person-badge person-badge-active"
                  : "person-badge"
              }
            >
              {person.mandateStatus}
              {person.electoralStatus ? ` · ${person.electoralStatus}` : ""}
            </span>
          ) : null}
        </div>
      </div>

      <dl className="person-facts">
        {person.civilName && person.civilName !== person.displayName ? (
          <div>
            <dt>Nome civil</dt>
            <dd>{person.civilName}</dd>
          </div>
        ) : null}
        <div>
          <dt>Naturalidade</dt>
          <dd>
            {person.birthCity
              ? `${person.birthCity}${
                  person.birthState ? `/${person.birthState}` : ""
                }`
              : "não coletado"}
          </dd>
        </div>
        <div>
          <dt>Escolaridade declarada</dt>
          <dd>{person.education ?? "não coletado"}</dd>
        </div>
        <div>
          <dt>Legislatura</dt>
          <dd>{person.legislature ?? "não coletado"}</dd>
        </div>
      </dl>

      <RepresentativeTrajectory
        currentMandate={{
          office: "Deputado(a) federal em exercício",
          period: person.legislature ? `${person.legislature}ª legislatura` : "legislatura não informada",
          status: person.mandateStatus
            ? `${person.mandateStatus}${person.electoralStatus ? ` · condição eleitoral atual: ${person.electoralStatus}` : ""}`
            : "Situação atual publicada pela Câmara",
          sourceLabel: "Câmara dos Deputados",
          sourceUrl: camaraUrl,
        }}
        votes={voteLinks}
      />
      <RepresentativeTransferSummary summary={transferSummary} />
      <StateLoaContributionTimeline rows={stateLoaContributions} />

      <p className="act-evidence">
        <a href={camaraUrl} target="_blank" rel="noreferrer">
          Perfil oficial na Câmara
        </a>
        {person.email ? ` · ${person.email}` : ""} · coletado em{" "}
        {dateFormatter.format(new Date(person.collectedAt))}
      </p>
    </article>
  );
}

function CouncillorCard({
  person,
  voteLinks,
}: Readonly<{
  person: Councillor;
  voteLinks: readonly RepresentativeVote[];
}>) {
  return (
    <article className="person-card" aria-label="Vereador">
      <div className="person-head">
        {person.photoUrl ? (
          // Foto oficial publicada pela própria Câmara Municipal.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="person-photo"
            src={person.photoUrl}
            alt=""
            width={72}
            height={96}
            loading="lazy"
          />
        ) : (
          <span className="person-photo person-photo-empty" aria-hidden="true" />
        )}
        <div>
          <h2>{person.displayName}</h2>
          <p className="person-role">
            Vereador(a) de Barreiras
            {person.party ? ` · ${person.party}` : ""}
          </p>
          {person.mandates ? (
            <span className="person-badge">{person.mandates}</span>
          ) : null}
        </div>
      </div>

      <RepresentativeTrajectory
        currentMandate={{
          office: "Vereador(a) de Barreiras em exercício",
          period: "legislatura municipal 2025–2028",
          status: "Em exercício conforme a Câmara Municipal",
          sourceLabel: "Câmara Municipal de Barreiras",
          sourceUrl: person.sourceUrl,
        }}
        votes={voteLinks}
      />

      {person.biography ? (
        <details>
          <summary>Biografia publicada pela Câmara</summary>
          <p className="person-bio">{person.biography}</p>
        </details>
      ) : null}

      <p className="act-evidence">
        <a href={person.sourceUrl} target="_blank" rel="noreferrer">
          Ver no portal da Câmara
        </a>{" "}
        · coletado em{" "}
        {dateFormatter.format(new Date(person.collectedAt))}
      </p>
    </article>
  );
}

function StateRepresentativeCard({
  person,
  voteLinks,
  transferSummary,
  stateLoaContributions,
}: Readonly<{
  person: StateRepresentative;
  voteLinks: readonly RepresentativeVote[];
  transferSummary: ParliamentaryTransferRanking | null;
  stateLoaContributions: readonly StateLoaRepresentativeContribution[];
}>) {
  const initials = person.displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <article
      className="person-card"
      id={`state-${person.externalId}`}
      aria-label="Deputado estadual"
    >
      <div className="person-head">
        {person.photoUrl ? (
          // Foto oficial preservada a partir da página individual da ALBA.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="person-photo"
            src={person.photoUrl}
            alt=""
            width={72}
            height={96}
            loading="lazy"
          />
        ) : (
          <span className="person-photo person-photo-initials" aria-hidden="true">
            {initials}
          </span>
        )}
        <div>
          <h2>{person.displayName}</h2>
          <p className="person-role">Deputado(a) estadual da Bahia</p>
          <span className="person-badge person-badge-active">mandato publicado pela ALBA</span>
        </div>
      </div>
      <RepresentativeTrajectory
        currentMandate={{
          office: "Deputado(a) estadual em exercício",
          period: "legislatura estadual atual",
          status: "Perfil incluído na composição atual publicada pela ALBA",
          sourceLabel: "Assembleia Legislativa da Bahia",
          sourceUrl: person.profileUrl,
        }}
        votes={voteLinks}
      />
      <RepresentativeTransferSummary summary={transferSummary} />
      <StateLoaContributionTimeline rows={stateLoaContributions} />
      {person.education || person.professionalActivity || person.electiveMandate || person.parliamentaryActivity ? (
        <details className="person-biography">
          <summary>Biografia oficial publicada pela ALBA</summary>
          <dl className="person-facts">
            {person.education ? (
              <div>
                <dt>Formação educacional</dt>
                <dd>{person.education}</dd>
              </div>
            ) : null}
            {person.professionalActivity ? (
              <div>
                <dt>Atividade profissional</dt>
                <dd>{person.professionalActivity}</dd>
              </div>
            ) : null}
            {person.electiveMandate ? (
              <div>
                <dt>Mandato eletivo</dt>
                <dd>{person.electiveMandate}</dd>
              </div>
            ) : null}
            {person.parliamentaryActivity ? (
              <div>
                <dt>Atividade parlamentar</dt>
                <dd>{person.parliamentaryActivity}</dd>
              </div>
            ) : null}
          </dl>
          <p className="person-source-note">
            Texto transcrito da página individual da ALBA; não é avaliação do
            mandato nem verificação independente das declarações.
          </p>
        </details>
      ) : null}
      <p className="act-evidence">
        <a href={person.profileUrl} target="_blank" rel="noreferrer">
          Perfil oficial na ALBA
        </a>{" "}
        · coletado em {dateFormatter.format(new Date(person.collectedAt))}
      </p>
      {!person.photoUrl ? (
        <p className="person-source-note">
          A página individual consultada não publicou uma imagem oficial
          preservável para este perfil.
        </p>
      ) : null}
    </article>
  );
}

/* function ExecutiveActCard({
  profile,
}: Readonly<{ profile: ExecutiveSnapshot }>) {
  const actLabel = profile.actType === "nomeacao" ? "Nomeação" : "Exoneração";
  return (
    <article className="person-card" aria-label="Ato do Executivo municipal">
      <div className="person-head">
        <span className="person-photo person-photo-empty" aria-hidden="true" />
        <div>
          <h2>{profile.personName}</h2>
          <p className="person-role">
            {profile.positionTitle}
            {profile.positionSymbol ? ` · ${profile.positionSymbol}` : ""}
          </p>
          <span
            className={
              profile.actType === "nomeacao"
                ? "person-badge person-badge-active"
                : "person-badge"
            }
          >
            {actLabel}
          </span>
        </div>
      </div>
      {profile.organization ? (
        <p className="person-link-note">
          <strong>Órgão:</strong> {profile.organization}
        </p>
      ) : null}
      {profile.excerpt ? (
        <details>
          <summary>Trecho que sustenta o registro</summary>
          <p className="person-bio">“{profile.excerpt}”</p>
        </details>
      ) : null}
      <p className="act-evidence">
        {profile.gazetteUrl ? (
          <a href={profile.gazetteUrl} target="_blank" rel="noreferrer">
            Ver documento oficial
          </a>
        ) : (
          <span>Documento preservado no acervo verificável</span>
        )}{" "}
        · ato em {profile.gazetteDate ?? "data não informada"} · hash{" "}
        {profile.artifactSha256.slice(0, 12)}…
      </p>
    </article>
  );
} */

function ExecutiveProfileCard({
  profile,
  voteLinks,
}: Readonly<{
  profile: ExecutiveProfile;
  voteLinks: readonly RepresentativeVote[];
}>) {
  const roleLabel =
    profile.role === "prefeito"
      ? "Prefeito de Barreiras"
      : profile.role === "vice-prefeito"
        ? "Vice-prefeito de Barreiras"
        : profile.departmentName ?? "Secretaria municipal";
  return (
    <article className="person-card" aria-label="Perfil do Executivo municipal">
      <div className="person-head">
        {profile.photoUrl ? (
          // Foto publicada pela própria Prefeitura.
          // eslint-disable-next-line @next/next/no-img-element
          <img className="person-photo" src={profile.photoUrl} alt="" width={72} height={96} loading="lazy" />
        ) : (
          <span className="person-photo person-photo-empty" aria-hidden="true" />
        )}
        <div>
          <h2>{profile.displayName}</h2>
          <p className="person-role">{roleLabel}</p>
          <span className="person-badge person-badge-active">perfil oficial</span>
        </div>
      </div>
      {profile.role === "prefeito" || profile.role === "vice-prefeito" ? (
        <RepresentativeTrajectory
          currentMandate={{
            office: roleLabel,
            period: "gestão municipal 2025–2028",
            status: "Perfil atual publicado pela Prefeitura",
            sourceLabel: "Prefeitura de Barreiras",
            sourceUrl: profile.profileUrl,
          }}
          votes={voteLinks}
        />
      ) : null}
      {profile.sourceExcerpt ? (
        <details>
          <summary>O que a Prefeitura publicou</summary>
          <p className="person-bio">{profile.sourceExcerpt}</p>
        </details>
      ) : null}
      <p className="act-evidence">
        <a href={profile.profileUrl} target="_blank" rel="noreferrer">
          Ver perfil oficial
        </a>{" "}
        · página consultada em {dateFormatter.format(new Date(profile.collectedAt))}
      </p>
    </article>
  );
}

function CandidateVoteCard({ vote }: Readonly<{ vote: TseVote }>) {
  return (
    <article className="person-card" aria-label="Candidatura com votação em Barreiras">
      <div className="person-head">
        <span className="person-photo person-photo-empty" aria-hidden="true" />
        <div>
          <h2>{vote.ballotName ?? vote.displayName ?? "Candidatura identificada pelo TSE"}</h2>
          <p className="person-role">
            {vote.office ?? "Cargo não informado"} · eleição {vote.electionYear} · {vote.turnNumber}º turno
          </p>
          {vote.party ? <span className="person-badge">{vote.party}</span> : null}
        </div>
      </div>
      <dl className="person-facts">
        <div>
          <dt>Votos em Barreiras</dt>
          <dd>{vote.votesInBarreiras.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Zonas somadas</dt>
          <dd>{vote.zones.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Situação no TSE</dt>
          <dd>{vote.situation ?? "não informado"}</dd>
        </div>
        <div>
          <dt>Número de urna</dt>
          <dd>{vote.candidateNumber ?? "não informado"}</dd>
        </div>
      </dl>
      <p className="person-link-note">
        Este é um registro de votação municipal por candidatura. Não representa
        avaliação de mandato, patrimônio ou atuação posterior.
      </p>
      <p className="act-evidence">
        Fonte: dados eleitorais do TSE · coletado em{" "}
        {dateFormatter.format(new Date(vote.collectedAt))}
      </p>
    </article>
  );
}

export default async function RepresentativesPage() {
  const [
    result,
    councillorsResult,
    stateResult,
    votesResult,
    executiveProfilesResult,
    representativeVotesResult,
    transferRankingsResult,
    stateLoaContributionsResult,
    legislatureRankingsResult,
  ] = await Promise.all([
    getFederalRepresentatives(),
    getMunicipalCouncillors(),
    getStateRepresentatives(),
    getTseBarreirasVotes(),
    getExecutiveProfiles(),
    getRepresentativeVotes(),
    getPublicParliamentaryTransferRankings(),
    getPublicStateLoaRepresentativeContributions(),
    getPublicParliamentaryLegislatureRankings(),
  ]);
  const legacyVotes = votesResult.state === "available" ? votesResult.votes : [];
  const representativeVotes =
    representativeVotesResult.state === "available"
      ? representativeVotesResult.votes
      : [];
  const transferRankings =
    transferRankingsResult.state === "available"
      ? transferRankingsResult.people
      : [];
  const stateLoaContributions =
    stateLoaContributionsResult.state === "available"
      ? stateLoaContributionsResult.contributions
      : [];
  const legislatureRankingGroups =
    legislatureRankingsResult.state === "available"
      ? legislatureRankingsResult.groups
      : null;

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário traduzido</a>
            <a href="/recursos">Recursos</a>
            <a href="/licitacoes">Licitações</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section section-representatives" aria-labelledby="people-title">
        <div className="section-heading">
          <span className="eyebrow">Registro público, não avaliação</span>
          <h1 id="people-title">Quem representa Barreiras</h1>
          <p>
            Perfis construídos apenas com registros oficiais, campo a campo
            com fonte e data. Não há nota ou julgamento: os rankings financeiros
            usam critérios objetivos e explicados; quando um
            dado não foi coletado, está escrito &ldquo;não coletado&rdquo; —
            ausência de informação nunca é apresentada como elogio ou
            defeito.
          </p>
        </div>

        <div className="coverage-note" role="note">
          <strong>Cobertura desta página, hoje</strong>
          <ul>
            <li>
              <strong>Prefeitura</strong>: atos aprovados de nomeação e
              exoneração aparecem no primeiro recorte abaixo; o cadastro
              completo do Executivo continua em construção.
            </li>
            <li>
              <strong>Vereadores</strong>: os que a Câmara Municipal publica
              no portal oficial — nome, partido, mandatos e foto, com a
              bandeira e a biografia atribuídas à própria Câmara.
            </li>
            <li>
              <strong>Deputados estaduais</strong>: perfis atuais publicados pela
              ALBA; a votação recebida em Barreiras aparece separadamente por
              eleição.
            </li>
            <li>
              <strong>Deputados federais</strong>: parlamentares em exercício pela
              Bahia na API aberta da Câmara dos Deputados, com legislatura e
              situação oficiais.
            </li>
            <li>
              <strong>Histórico eleitoral</strong>: candidaturas registradas no
              TSE, separadas por pleito, cargo, turno e resultado daquele ano.
              Candidatura não é apresentada como mandato atual.
            </li>
            <li>
              <strong>Vínculo com Barreiras</strong>: votação nominal no
              município (TSE) e emendas destinadas ao município são exibidas
              em painéis separados, com números e fontes oficiais.
            </li>
          </ul>
        </div>

        <nav className="representation-jump-nav" aria-label="Ir para uma seção">
          <a href="#executivo">Executivo</a>
          <a href="#vereadores">Vereadores</a>
          <a href="#estaduais">Estaduais</a>
          <a href="#federais">Federais</a>
          <a href="#emendas-por-legislatura">Emendas por legislatura</a>
          <a href="#vinculo">Vínculo com Barreiras</a>
          <a href="/recursos">Emendas e recursos</a>
        </nav>

        <div className="representation-overview" aria-label="Resumo da cobertura">
          <div>
            <strong>{countLabel(councillorsResult.state === "available" ? councillorsResult.councillors.length : null)}</strong>
            <span>vereadores atuais</span>
          </div>
          <div>
            <strong>{countLabel(stateResult.state === "available" ? stateResult.representatives.length : null)}</strong>
            <span>mandatos estaduais atuais</span>
          </div>
          <div>
            <strong>{countLabel(result.state === "available" ? result.representatives.length : null)}</strong>
            <span>mandatos federais atuais</span>
          </div>
          <div>
            <strong>{countLabel(votesResult.state === "available" ? votesResult.votes.length : null)}</strong>
            <span>candidaturas históricas</span>
          </div>
        </div>

        <LegislatureTransferRankings groups={legislatureRankingGroups} />

        <div id="executivo" className="representation-block representation-block-municipal-leadership">
          <section aria-labelledby="executive-title">
            <div className="section-heading">
              <span className="eyebrow">Prefeitura de Barreiras</span>
              <h2 id="executive-title">Prefeito, vice e secretarias</h2>
              <p>
                Perfis oficiais da Prefeitura, separados da linha do tempo de
                nomeações e exonerações. A fonte, a data da consulta e o trecho
                publicado ficam disponíveis em cada cartão.
              </p>
            </div>
            {executiveProfilesResult.state === "available" && executiveProfilesResult.profiles.length > 0 ? (
              <div className="person-grid">
                {executiveProfilesResult.profiles.map((profile) => (
                  <ExecutiveProfileCard
                    key={profile.profileKey}
                    profile={profile}
                    voteLinks={votesForRepresentative(
                      representativeVotes,
                      "executive",
                      profile.profileKey,
                    )}
                  />
                ))}
              </div>
            ) : (
              <div className="collection-unavailable" role="status">
                <div>
                  <strong>Cadastro do Executivo em atualização</strong>
                  <p>
                    O perfil oficial será exibido assim que a próxima coleta da
                    Prefeitura for preservada e validada.
                  </p>
                </div>
              </div>
            )}
          </section>
          {/* <section aria-labelledby="executive-acts-title">
            <div className="section-heading">
              <span className="eyebrow">Diário Oficial</span>
              <h2 id="executive-acts-title">Atos do Executivo municipal</h2>
              <p>
                Nomeações e exonerações aparecem somente quando sustentadas por
                ato oficial preservado.
              </p>
            </div>
            {executiveResult.state === "unavailable" ? (
              <div className="collection-unavailable" role="status">
                <div>
                  <strong>Atos do Executivo temporariamente indisponíveis</strong>
                  <p>
                    Isso representa falha de consulta, não ausência de
                    nomeações ou exonerações. Tente novamente em alguns minutos.
                  </p>
                </div>
              </div>
            ) : executiveSnapshot.length === 0 ? (
              <div className="collection-unavailable" role="status">
                <div>
                  <strong>O primeiro recorte do Executivo está em revisão</strong>
                  <p>
                    Os atos só aparecem nesta página depois de preservação,
                    extração e aprovação editorial.
                  </p>
                  <a href="/atos">Acompanhar atos publicados →</a>
                </div>
              </div>
            ) : (
              <>
                <p className="acts-count" role="status">
                  {executiveSnapshot.length.toLocaleString("pt-BR")} cargos com
                  ato mais recente no recorte aprovado
                </p>
                <div className="person-grid">
                  {executiveSnapshot.slice(0, 24).map((profile) => (
                    <ExecutiveActCard key={profile.key} profile={profile} />
                  ))}
                </div>
                {executiveSnapshot.length > 24 ? (
                  <p className="hero-note">
                    Exibindo os 24 atos mais recentes. O histórico completo está
                    disponível em <a href="/atos">Atos públicos</a>.
                  </p>
                ) : null}
              </>
            )}
          </section> */}
          <div className="collection-unavailable" role="note">
            <div>
              <strong>Atos públicos ficam em uma página própria</strong>
              <p>
                Acompanhe nomeações, exonerações e demais registros do Diário
                Oficial em uma linha do tempo com busca, filtros e documento
                original.
              </p>
              <a href="/atos">Abrir Atos públicos →</a>
            </div>
          </div>
        </div>

        <section id="vereadores" className="representation-block representation-block-councillors" aria-labelledby="councillors-title">
        <div className="section-heading">
          <span className="eyebrow">Câmara Municipal</span>
          <h2 id="councillors-title">Mandatos municipais atuais</h2>
          <p>
            Composição publicada pelo portal oficial da Câmara. Bandeira e
            biografia são textos da própria Casa, reproduzidos com
            atribuição — não são avaliação nossa.
          </p>
        </div>

        {councillorsResult.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Lista de vereadores indisponível</strong>
              <p>
                Isso representa uma falha de consulta, não ausência de dados.
              </p>
            </div>
          </div>
        ) : councillorsResult.councillors.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Vereadores ainda não coletados</strong>
              <p>
                A coleta no portal da Câmara está configurada e roda
                semanalmente.
              </p>
            </div>
          </div>
        ) : (
          <>
            <p className="acts-count" role="status">
              {councillorsResult.councillors.length.toLocaleString("pt-BR")}{" "}
              vereadores em exercício
            </p>
            <div className="person-grid">
              {councillorsResult.councillors.map((person) => (
                <CouncillorCard
                  key={person.councillorId}
                  person={person}
                  voteLinks={votesForRepresentative(
                    representativeVotes,
                    "municipal",
                    person.councillorId,
                  )}
                />
              ))}
            </div>
          </>
        )}
        </section>

        <section id="estaduais" className="representation-block representation-block-state" aria-labelledby="state-title">
          <div className="section-heading">
            <span className="eyebrow">Assembleia Legislativa da Bahia</span>
            <h2 id="state-title">Mandatos estaduais atuais</h2>
            <p>
              Composição em exercício publicada pela ALBA. Quem disputou esse
              cargo em outro pleito aparece no histórico eleitoral abaixo; esta
              lista não atribui representação de Barreiras sem evidência
              municipal específica.
            </p>
          </div>
          {stateResult.state === "unavailable" ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Lista estadual temporariamente indisponível</strong>
                <p>
                  Isso representa uma falha de consulta, não ausência de
                  deputados na fonte oficial.
                </p>
              </div>
            </div>
          ) : stateResult.representatives.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Lista estadual ainda não coletada</strong>
                <p>
                  A coleta da ALBA está configurada e aparecerá depois da
                  primeira execução válida.
                </p>
              </div>
            </div>
          ) : (
            <>
              <p className="acts-count" role="status">
                {stateResult.representatives.length.toLocaleString("pt-BR")} perfis
                atuais publicados pela ALBA
              </p>
              <details className="representation-collapsible representation-directory-collapsible">
                <summary>
                  <span>
                    <strong>Ver perfis estaduais</strong>
                  </span>
                  <span className="representation-collapsible-meta">
                    {stateResult.representatives.length.toLocaleString("pt-BR")} perfis · abrir
                  </span>
                </summary>
                <div className="person-grid">
                  {stateResult.representatives.map((person) => (
                    <StateRepresentativeCard
                      key={person.externalId}
                      person={person}
                      voteLinks={votesForRepresentative(
                        representativeVotes,
                        "state",
                        person.externalId,
                      )}
                      transferSummary={transferSummaryForRepresentative(
                        transferRankings,
                        "state",
                        person.externalId,
                      )}
                      stateLoaContributions={stateLoaContributionsForRepresentative(
                        stateLoaContributions,
                        "state",
                        person.externalId,
                      )}
                    />
                  ))}
                </div>
              </details>
            </>
          )}
        </section>

        <section id="federais" className="representation-block representation-block-federal" aria-labelledby="federal-title">
          <div className="section-heading">
            <span className="eyebrow">Câmara dos Deputados</span>
            <h2 id="federal-title">Mandatos federais atuais</h2>
            <p>
              Pessoas em exercício pela Bahia na 57ª legislatura, conforme a
              API oficial da Câmara dos Deputados. Candidaturas anteriores ou a
              outros cargos ficam no histórico eleitoral, sem alterar esta lista.
            </p>
          </div>
          {result.state === "unavailable" ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Lista temporariamente indisponível</strong>
                <p>
                  Isso representa uma falha de consulta, não ausência de dados.
                  Tente novamente em alguns minutos.
                </p>
              </div>
            </div>
          ) : result.representatives.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Os primeiros perfis estão a caminho</strong>
                <p>
                  A coleta na Câmara dos Deputados está configurada e os
                  perfis aparecerão aqui na próxima execução automática.
                </p>
              </div>
            </div>
          ) : (
            <>
              <p className="acts-count" role="status">
                {result.representatives.length.toLocaleString("pt-BR")}{" "}
                perfis em exercício publicados pela Câmara dos Deputados
              </p>
              <details className="representation-collapsible representation-directory-collapsible">
                <summary>
                  <span>
                    <strong>Ver perfis federais</strong>
                  </span>
                  <span className="representation-collapsible-meta">
                    {result.representatives.length.toLocaleString("pt-BR")} perfis · abrir
                  </span>
                </summary>
                <div className="person-grid">
                  {result.representatives.map((person) => (
                    <RepresentativeCard
                      key={person.externalId}
                      person={person}
                      voteLinks={votesForRepresentative(
                        representativeVotes,
                        "federal",
                        person.externalId,
                      )}
                      transferSummary={transferSummaryForRepresentative(
                        transferRankings,
                        "federal",
                        person.externalId,
                      )}
                      stateLoaContributions={stateLoaContributionsForRepresentative(
                        stateLoaContributions,
                        "federal",
                        person.externalId,
                      )}
                    />
                  ))}
                </div>
              </details>
            </>
          )}
        </section>

        <section id="vinculo" className="representation-block representation-block-candidates" aria-labelledby="candidates-title">
          {votesResult.state === "available" ? (
            <TerritorialVotesStudy votes={votesResult.votes} />
          ) : (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Dados eleitorais temporariamente indisponíveis</strong>
                <p>Isso representa falha de consulta, não ausência de candidaturas.</p>
                <a href="https://divulgacandcontas.tse.jus.br/" target="_blank" rel="noreferrer">
                  Consultar DivulgaCandContas/TSE →
                </a>
              </div>
            </div>
          )}
        </section>

        {votesResult.state === "available" && false ? <details id="candidaturas" className="representation-collapsible">
          <summary>
            <span>
              <span className="eyebrow">Histórico eleitoral</span>
              <strong>Candidaturas e estudos</strong>
            </span>
            <span className="representation-collapsible-meta">
              {countLabel(legacyVotes.length)} registros · abrir
            </span>
          </summary>
        <section className="representation-block representation-block-candidates" aria-labelledby="candidates-title">
          <div className="section-heading">
            <span className="eyebrow">Eleições e vínculo municipal</span>
            <h2 id="candidates-title">Candidaturas com votação em Barreiras</h2>
            <p>
              Resultado nominal agregado pelo código da candidatura, conforme o
              TSE. A lista não é o cadastro completo de candidatos e não avalia
              pessoas ou mandatos.
            </p>
          </div>
          {votesResult.state === "unavailable" ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Dados eleitorais temporariamente indisponíveis</strong>
                <p>
                  Isso representa falha de consulta ou ausência de coleta
                  válida, não ausência de candidaturas.
                </p>
                <a href="https://divulgacandcontas.tse.jus.br/" target="_blank" rel="noreferrer">
                  Consultar DivulgaCandContas/TSE →
                </a>
              </div>
            </div>
          ) : legacyVotes.length === 0 ? (
            <div className="collection-unavailable" role="status">
              <div>
                <strong>Votação municipal ainda não coletada</strong>
                <p>
                  A coleta do TSE aparecerá aqui depois da primeira execução
                  válida para um pleito.
                </p>
              </div>
            </div>
          ) : (
            <>
              <p className="acts-count" role="status">
                {legacyVotes.length.toLocaleString("pt-BR")} registros de votação municipal
              </p>
              <div className="person-grid">
                {legacyVotes.map((vote) => (
                  <CandidateVoteCard key={`${vote.electionYear}-${vote.candidateId}-${vote.turnNumber}`} vote={vote} />
                ))}
              </div>
            </>
          )}
        </section>
        </details> : null}

        <p className="hero-note">
          Metodologia: identidade unificada apenas por identificador oficial
          (nunca por nome, para não confundir homônimos); vínculo territorial
          declarado e mensurável; nenhum dado pessoal desnecessário é
          publicado — o CPF que a fonte oficial divulga não é reproduzido
          aqui. Encontrou um erro?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/representantes&labels=correcao"
            target="_blank"
            rel="noreferrer"
          >
            Abra um pedido público de correção
          </a>
          .
        </p>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="/">
              <span>Barreiras 360</span>
            </a>
            <p>
              Informação pública de Barreiras para acompanhar a cidade com
              clareza.
            </p>
          </div>
          <div className="footer-status">
            <span className="status-dot" />
            Perfis com fonte por campo e rankings financeiros com metodologia
          </div>
        </div>
      </footer>
    </main>
  );
}
