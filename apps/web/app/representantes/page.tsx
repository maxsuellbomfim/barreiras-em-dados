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

function RepresentativeCard({
  person,
}: Readonly<{ person: FederalRepresentative }>) {
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

      <p className="person-link-note">
        <strong>Vínculo com Barreiras:</strong> eleito(a) pelo estado da
        Bahia. A base municipal do TSE já foi preservada; a associação
        individual entre votação em Barreiras e este perfil ainda passa por
        consolidação e revisão.
      </p>

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

function CouncillorCard({ person }: Readonly<{ person: Councillor }>) {
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
}: Readonly<{ person: StateRepresentative }>) {
  return (
    <article className="person-card" aria-label="Deputado estadual">
      <div className="person-head">
        <span className="person-photo person-photo-empty" aria-hidden="true" />
        <div>
          <h2>{person.displayName}</h2>
          <p className="person-role">Deputado(a) estadual da Bahia</p>
          <span className="person-badge person-badge-active">mandato publicado pela ALBA</span>
        </div>
      </div>
      <p className="person-link-note">
        <strong>Vínculo com Barreiras:</strong> ainda não consolidado nesta
        projeção. A presença na Assembleia não é tratada como representação
        exclusiva do município.
      </p>
      <p className="act-evidence">
        <a href={person.profileUrl} target="_blank" rel="noreferrer">
          Perfil oficial na ALBA
        </a>{" "}
        · coletado em {dateFormatter.format(new Date(person.collectedAt))}
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

function FutureCoverage({
  eyebrow,
  title,
  description,
  sourceLabel,
  sourceUrl,
}: Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  sourceLabel: string;
  sourceUrl: string;
}>) {
  return (
    <section className="representation-future" aria-labelledby={`${title}-title`}>
      <div className="section-heading">
        <span className="eyebrow">{eyebrow}</span>
        <h2 id={`${title}-title`}>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="collection-unavailable" role="status">
        <div>
          <strong>Fonte em preparação</strong>
          <p>
            Esta seção só será preenchida depois que a fonte oficial for
            coletada, conferida e ligada a evidências. Ausência de dados não
            será apresentada como zero ou como avaliação.
          </p>
          <a href={sourceUrl} target="_blank" rel="noreferrer">
            Consultar {sourceLabel} →
          </a>
        </div>
      </div>
    </section>
  );
}

export default async function RepresentativesPage() {
  const [result, councillorsResult, stateResult, votesResult] = await Promise.all([
    getFederalRepresentatives(),
    getMunicipalCouncillors(),
    getStateRepresentatives(),
    getTseBarreirasVotes(),
  ]);

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
              <strong>Prefeitura</strong>: prefeito, vice e secretários estão no
              primeiro recorte de fontes em preparação.
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
          <a href="#candidaturas">Candidaturas</a>
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
          <FutureCoverage
            eyebrow="Prefeitura"
            title="Prefeito, vice-prefeito e secretários"
            description="A composição do Executivo será ligada aos atos de nomeação, vigência, remuneração e atuação de cada órgão."
            sourceLabel="Prefeitura de Barreiras"
            sourceUrl="https://barreiras.ba.gov.br/"
          />
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
            <div className="person-grid">
              {result.representatives.map((person) => (
                <RepresentativeCard key={person.externalId} person={person} />
              ))}
            </div>
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
                <CouncillorCard key={person.councillorId} person={person} />
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
              <div className="person-grid">
                {stateResult.representatives.map((person) => (
                  <StateRepresentativeCard key={person.externalId} person={person} />
                ))}
              </div>
            </>
          )}
        </section>

        <details id="candidaturas" className="representation-collapsible">
          <summary>
            <span>
              <span className="eyebrow">Histórico eleitoral</span>
              <strong>Candidaturas e estudos</strong>
            </span>
            <span className="representation-collapsible-meta">
              {countLabel(votesResult.state === "available" ? votesResult.votes.length : null)} registros · abrir
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
          ) : votesResult.votes.length === 0 ? (
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
                {votesResult.votes.length.toLocaleString("pt-BR")} registros de votação municipal
              </p>
              <div className="person-grid">
                {votesResult.votes.map((vote) => (
                  <CandidateVoteCard key={`${vote.electionYear}-${vote.candidateId}-${vote.turnNumber}`} vote={vote} />
                ))}
              </div>
            </>
          )}
        </section>
        </details>

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
