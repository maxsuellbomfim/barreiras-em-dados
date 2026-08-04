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
import {
  getCamaraLegislativeAuthorSummary,
  type CamaraLegislativeAuthorSummary,
} from "../../lib/camara-legislative";
import TerritorialVotesStudy from "./territorial-votes-study";
import {
  getExecutiveProfiles,
  type ExecutiveProfile,
} from "../../lib/executive-profiles";

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

function officialNameKey(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleUpperCase("pt-BR");
}

function legislativeAuthorMatch(
  personName: string,
  summaries: readonly CamaraLegislativeAuthorSummary[],
): CamaraLegislativeAuthorSummary | null {
  // A normalização só torna maiúsculas, acentos e espaços comparáveis; não
  // transforma o nome em uma identificação civil nem resolve homônimos.
  const personKey = officialNameKey(personName);
  return (
    summaries.find((summary) => officialNameKey(summary.authorName) === personKey) ??
    null
  );
}

function countLabel(count: number | null): string {
  return count === null ? "—" : count.toLocaleString("pt-BR");
}

function RepresentativeVoteSummary({
  votes,
}: Readonly<{ votes: readonly RepresentativeVote[] }>) {
  return (
    <div className="person-vote-summary" aria-label="Votação em Barreiras">
      <div className="person-vote-summary-heading">
        <strong>Votação em Barreiras</strong>
        <span className="person-vote-summary-badge">
          {votes.length > 0
            ? votes.some((vote) => vote.voteScope === "ticket")
              ? "chapa majoritária"
              : "vínculo confirmado"
            : "em consolidação"}
        </span>
      </div>
      {votes.length > 0 ? (
        <>
          <ul>
            {votes.map((vote) => (
              <li key={`${vote.electionYear}-${vote.candidateId}-${vote.turnNumber}`}>
                <span>
                  {vote.electionYear} · {vote.turnNumber}º turno
                  <small className="person-vote-candidate-name">
                    {vote.ballotName ?? vote.displayName ?? "candidatura no TSE"}
                  </small>
                </span>
                <strong>
                  {vote.votesInBarreiras.toLocaleString("pt-BR")} {vote.voteScope === "ticket" ? "votos da chapa" : "votos"}
                </strong>
              </li>
            ))}
          </ul>
          {votes.some((vote) => vote.voteScope === "ticket") ? (
            <p>{votes.find((vote) => vote.voteScope === "ticket")?.scopeNote}</p>
          ) : null}
        </>
      ) : (
        <p>
          Ainda não há um vínculo eleitoral aprovado por identificador oficial
          para este perfil. O registro não é presumido por semelhança de nome.
        </p>
      )}
      <a href="#vinculo">Ver o estudo territorial completo →</a>
    </div>
  );
}

function RepresentativeCard({
  person,
  voteLinks,
}: Readonly<{
  person: FederalRepresentative;
  voteLinks: readonly RepresentativeVote[];
}>) {
  const camaraUrl = `https://www.camara.leg.br/deputados/${person.externalId}`;
  return (
    <article className="person-card" aria-label="Representante">
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

      <RepresentativeVoteSummary votes={voteLinks} />

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
  legislativeAuthor,
}: Readonly<{
  person: Councillor;
  voteLinks: readonly RepresentativeVote[];
  legislativeAuthor: CamaraLegislativeAuthorSummary | null;
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

      {person.mainAgenda ? (
        <p className="person-link-note">
          <strong>Principal bandeira, segundo a Câmara:</strong>{" "}
          {person.mainAgenda}
        </p>
      ) : null}

      <RepresentativeVoteSummary votes={voteLinks} />

      <details className="person-legislative-summary">
        <summary>Leis e indicações atribuídas pela Câmara</summary>
        {legislativeAuthor ? (
          <>
            <p>
              O acervo legislativo informa <strong>{legislativeAuthor.itemCount}</strong>{" "}
              registro(s) com este texto de autoria no recorte publicado. Isso
              não confirma a identidade em caso de homônimo.
            </p>
            <a
              href={`/camara?author=${encodeURIComponent(legislativeAuthor.authorName)}`}
            >
              Abrir pesquisa pelo nome publicado →
            </a>
          </>
        ) : (
          <p>
            A Câmara ainda não publicou autoria com correspondência exata neste
            acervo. Nenhuma associação foi feita por semelhança de nome.
          </p>
        )}
      </details>

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
}: Readonly<{
  person: StateRepresentative;
  voteLinks: readonly RepresentativeVote[];
}>) {
  const initials = person.displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <article className="person-card" aria-label="Deputado estadual">
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
      <RepresentativeVoteSummary votes={voteLinks} />
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
        <RepresentativeVoteSummary votes={voteLinks} />
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
    legislativeAuthorSummary,
  ] = await Promise.all([
    getFederalRepresentatives(),
    getMunicipalCouncillors(),
    getStateRepresentatives(),
    getTseBarreirasVotes(),
    getExecutiveProfiles(),
    getRepresentativeVotes(),
    getCamaraLegislativeAuthorSummary(),
  ]);
  const legacyVotes = votesResult.state === "available" ? votesResult.votes : [];
  const representativeVotes =
    representativeVotesResult.state === "available"
      ? representativeVotesResult.votes
      : [];

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário traduzido</a>
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
            com fonte e data. Não há nota, ranking ou julgamento: quando um
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
              <strong>Deputados estaduais</strong>: serão ligados à fonte oficial
              da ALBA e a um vínculo territorial documentado.
            </li>
            <li>
              <strong>Deputados federais</strong>: eleitos pela Bahia, da API
              aberta da Câmara dos Deputados — já disponíveis abaixo.
            </li>
            <li>
              <strong>Candidatos</strong>: aparecerão somente quando registrados
              no TSE, com situação atualizada por eleição.
            </li>
            <li>
              <strong>Vínculo com Barreiras</strong>: será apresentado com
              votação nominal no município (TSE), emendas destinadas ao
              município e demais registros oficiais — números, não opinião.
            </li>
          </ul>
        </div>

        <nav className="representation-jump-nav" aria-label="Ir para uma seção">
          <a href="#executivo">Executivo</a>
          <a href="#vereadores">Vereadores</a>
          <a href="#estaduais">Estaduais</a>
          <a href="#federais">Federais</a>
          <a href="#vinculo">Vínculo com Barreiras</a>
        </nav>

        <div className="representation-overview" aria-label="Resumo da cobertura">
          <div>
            <strong>{countLabel(councillorsResult.state === "available" ? councillorsResult.councillors.length : null)}</strong>
            <span>vereadores atuais</span>
          </div>
          <div>
            <strong>{countLabel(stateResult.state === "available" ? stateResult.representatives.length : null)}</strong>
            <span>deputados estaduais</span>
          </div>
          <div>
            <strong>{countLabel(result.state === "available" ? result.representatives.length : null)}</strong>
            <span>deputados federais</span>
          </div>
          <div>
            <strong>{countLabel(votesResult.state === "available" ? votesResult.votes.length : null)}</strong>
            <span>registros eleitorais</span>
          </div>
        </div>

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

        <section id="federais" className="representation-block representation-block-federal" aria-labelledby="federal-title">
          <div className="section-heading">
            <span className="eyebrow">Câmara dos Deputados</span>
            <h2 id="federal-title">Deputados federais</h2>
            <p>
              Parlamentares eleitos pela Bahia, com vínculo territorial
              apresentado separadamente da representação municipal.
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
              deputados federais eleitos pela Bahia
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
                  />
                ))}
              </div>
            </details>
          </>
          )}
        </section>

        <section id="vereadores" className="representation-block representation-block-councillors" aria-labelledby="councillors-title">
        <div className="section-heading">
          <span className="eyebrow">Câmara Municipal</span>
          <h2 id="councillors-title">Vereadores de Barreiras</h2>
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
                  legislativeAuthor={legislativeAuthorMatch(
                    person.displayName,
                    legislativeAuthorSummary,
                  )}
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
            <h2 id="state-title">Deputados estaduais</h2>
            <p>
              Composição publicada pela ALBA, com vínculo territorial tratado
              separadamente. A lista não afirma que qualquer parlamentar
              representa Barreiras sem evidência municipal específica.
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
                {stateResult.representatives.length.toLocaleString("pt-BR")} deputados
                estaduais publicados pela ALBA
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
            Perfis com fonte por campo, sem ranking de pessoas
          </div>
        </div>
      </footer>
    </main>
  );
}
