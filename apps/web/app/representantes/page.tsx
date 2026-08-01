import type { Metadata } from "next";

import {
  getMunicipalCouncillors,
  type Councillor,
} from "../../lib/councillors";
import {
  getFederalRepresentatives,
  type FederalRepresentative,
} from "../../lib/representatives";

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
        Bahia. A votação nominal recebida em Barreiras — o vínculo local
        mensurável — ainda não foi coletada do TSE.
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

export default async function RepresentativesPage() {
  const [result, councillorsResult] = await Promise.all([
    getFederalRepresentatives(),
    getMunicipalCouncillors(),
  ]);

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras em Dados">
            <span>← Barreiras em Dados</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário traduzido</a>
            <a href="/licitacoes">Licitações</a>
            <a href="/atos">Atos</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="people-title">
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
              <strong>Deputados federais</strong>: eleitos pela Bahia, da API
              aberta da Câmara dos Deputados — já disponível abaixo.
            </li>
            <li>
              <strong>Vereadores</strong>: os que a Câmara Municipal publica
              no portal oficial — nome, partido, mandatos e foto, com a
              bandeira e a biografia atribuídas à própria Câmara.
            </li>
            <li>
              <strong>Deputados estaduais, secretários e candidaturas</strong>:
              em construção. Cada grupo entra quando houver fonte oficial e
              critério de vínculo verificável (ADR 0014).
            </li>
            <li>
              <strong>Vínculo com Barreiras</strong>: será medido pela
              votação nominal no município (TSE) e por emendas destinadas ao
              município — números, não opinião.
            </li>
          </ul>
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

        <div className="section-heading" style={{ marginTop: "3.5rem" }}>
          <span className="eyebrow">Câmara Municipal</span>
          <h2>Vereadores de Barreiras</h2>
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
              <span>Barreiras em Dados</span>
            </a>
            <p>
              Civic tech independente para tornar a informação pública de
              Barreiras mais acessível e verificável.
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
