const officialSources = [
  {
    name: "Diário Oficial",
    detail: "Atos publicados pela Prefeitura",
    href: "https://queridodiario.ok.org.br/cidades/ba-barreiras",
    tone: "blue",
  },
  {
    name: "Prefeitura",
    detail: "Portal de dados abertos do Executivo",
    href: "https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/",
    tone: "green",
  },
  {
    name: "Câmara Municipal",
    detail: "Portal de dados abertos do Legislativo",
    href: "https://portaldatransparencia.cmbarreiras.ba.gov.br/dados-abertos/",
    tone: "violet",
  },
  {
    name: "PNCP",
    detail: "Contratações públicas nacionais",
    href: "https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos",
    tone: "amber",
  },
] as const;

const publicTracks = [
  {
    eyebrow: "Primeiro",
    title: "Nomeações e exonerações",
    description:
      "Uma linha do tempo pesquisável, sempre ligada ao ato oficial e ao trecho que sustenta cada registro.",
    status: "Em construção",
  },
  {
    eyebrow: "Depois",
    title: "Licitações e contratos",
    description:
      "Do processo ao fornecedor: itens, resultados, contratos, documentos e histórico de alterações.",
    status: "Mapeado",
  },
  {
    eyebrow: "Na sequência",
    title: "Receitas e despesas",
    description:
      "Empenho, liquidação e pagamento explicados em linguagem comum, com cálculos reproduzíveis.",
    status: "Planejado",
  },
] as const;

const evidenceSteps = [
  {
    number: "01",
    title: "Coletar",
    copy: "Buscamos o dado diretamente em uma fonte pública identificada.",
  },
  {
    number: "02",
    title: "Preservar",
    copy: "Guardamos uma cópia bruta com URL, data de coleta e hash SHA-256.",
  },
  {
    number: "03",
    title: "Entender",
    copy: "Normalizamos campos sem substituir nem apagar o documento original.",
  },
  {
    number: "04",
    title: "Revisar",
    copy: "Conteúdo sensível ou reputacional só avança após revisão humana.",
  },
  {
    number: "05",
    title: "Publicar",
    copy: "O cidadão vê a informação, a fonte e as limitações lado a lado.",
  },
] as const;

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

function ExternalArrow() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
    >
      <path
        d="M5 11 11 5M6 5h5v5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ShieldCheck() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="24"
      height="24"
      fill="none"
    >
      <path
        d="M12 3 4.75 6v5.1c0 4.6 2.95 8.86 7.25 9.9 4.3-1.04 7.25-5.3 7.25-9.9V6L12 3Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="m8.8 12 2 2 4.4-4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function HomePage() {
  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="#inicio" aria-label="Barreiras em Dados">
            <BrandMark />
            <span>Barreiras em Dados</span>
          </a>

          <nav className="nav-links" aria-label="Navegação principal">
            <a href="#como-funciona">Como funciona</a>
            <a href="#fontes">Fontes</a>
            <a href="#construcao">Construção</a>
          </nav>

          <a className="nav-cta" href="#metodologia">
            Metodologia
          </a>
        </div>
      </header>

      <section className="hero" id="inicio" aria-labelledby="hero-title">
        <div className="ambient ambient-one" />
        <div className="ambient ambient-two" />
        <div className="hero-grid" aria-hidden="true" />

        <div className="hero-content">
          <div className="status-pill">
            <span className="status-dot" />
            Portal público em construção
          </div>

          <h1 id="hero-title">
            Barreiras,
            <br />
            <span>sem barreiras nos dados.</span>
          </h1>

          <p className="hero-copy">
            Informação pública municipal com fonte, contexto e linguagem que
            todo mundo entende.
          </p>

          <div className="hero-actions">
            <a className="button button-primary" href="#construcao">
              Ver o que estamos construindo
              <span aria-hidden="true">↓</span>
            </a>
            <a className="button button-secondary" href="#como-funciona">
              Entender a cadeia de evidências
            </a>
          </div>

          <p className="hero-note">
            Sem acusações automáticas. Sem ranking de pessoas. Todo registro
            publicado terá uma fonte verificável.
          </p>
        </div>

        <div className="hero-proof" aria-label="Estado técnico do projeto">
          <div className="proof-top">
            <div>
              <span className="proof-label">Cadeia de custódia</span>
              <strong>Ativa</strong>
            </div>
            <span className="proof-icon">
              <ShieldCheck />
            </span>
          </div>

          <div className="proof-document">
            <div className="document-head">
              <span />
              <span />
              <span />
            </div>
            <div className="document-line line-long" />
            <div className="document-line line-medium" />
            <div className="document-line line-short" />
            <div className="hash-row">
              <span>SHA-256 verificado</span>
              <code>cf1d…b0f1</code>
            </div>
          </div>

          <div className="proof-stats">
            <div>
              <strong>79</strong>
              <span>recursos oficiais catalogados</span>
            </div>
            <div>
              <strong>40</strong>
              <span>entidades na fundação de dados</span>
            </div>
            <div>
              <strong>1</strong>
              <span>artefato remoto verificado</span>
            </div>
          </div>

          <p className="proof-caption">
            Estes números descrevem a infraestrutura atual, não indicadores da
            gestão municipal.
          </p>
        </div>
      </section>

      <section
        className="section section-evidence"
        id="como-funciona"
        aria-labelledby="evidence-title"
      >
        <div className="section-heading">
          <span className="eyebrow">Evidência antes de interface</span>
          <h2 id="evidence-title">Do portal oficial até você.</h2>
          <p>
            Cada informação percorre uma trilha verificável. O dado original
            continua preservado mesmo quando uma correção é necessária.
          </p>
        </div>

        <ol className="evidence-flow">
          {evidenceSteps.map((step) => (
            <li key={step.number}>
              <span className="step-number">{step.number}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section
        className="section section-sources"
        id="fontes"
        aria-labelledby="sources-title"
      >
        <div className="section-heading heading-row">
          <div>
            <span className="eyebrow">Fontes documentadas</span>
            <h2 id="sources-title">A origem fica visível.</h2>
          </div>
          <p>
            Fonte oficial não significa ausência de erro. Por isso preservamos
            versões, registramos conflitos e mostramos as limitações.
          </p>
        </div>

        <div className="source-grid">
          {officialSources.map((source) => (
            <a
              className="source-card"
              href={source.href}
              target="_blank"
              rel="noreferrer"
              key={source.name}
            >
              <span className={`source-orb source-orb-${source.tone}`} />
              <div>
                <h3>{source.name}</h3>
                <p>{source.detail}</p>
              </div>
              <span className="source-arrow">
                <ExternalArrow />
              </span>
            </a>
          ))}
        </div>
      </section>

      <section
        className="section section-build"
        id="construcao"
        aria-labelledby="build-title"
      >
        <div className="section-heading section-heading-centered">
          <span className="eyebrow">Construção pública e gradual</span>
          <h2 id="build-title">Começamos pelo que pode ser comprovado.</h2>
          <p>
            O portal cresce por etapas pequenas. Nenhuma área será apresentada
            como concluída antes de passar por testes e revisão.
          </p>
        </div>

        <div className="track-grid">
          {publicTracks.map((track) => (
            <article className="track-card" key={track.title}>
              <div className="track-top">
                <span>{track.eyebrow}</span>
                <span className="track-status">{track.status}</span>
              </div>
              <h3>{track.title}</h3>
              <p>{track.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="principles" id="metodologia">
        <div className="principles-inner">
          <div className="principles-copy">
            <span className="eyebrow eyebrow-light">Compromisso público</span>
            <h2>Transparência também exige cuidado.</h2>
            <p>
              Uma anomalia é um sinal para análise, não prova de irregularidade.
              Fatos, inferências, hipóteses e alertas terão tratamentos
              visivelmente diferentes.
            </p>
          </div>

          <div className="principle-list">
            <div>
              <span>01</span>
              <p>Documento original e trecho de sustentação sempre acessíveis.</p>
            </div>
            <div>
              <span>02</span>
              <p>Cálculos financeiros feitos por código determinístico.</p>
            </div>
            <div>
              <span>03</span>
              <p>Revisão humana antes de conteúdo potencialmente reputacional.</p>
            </div>
            <div>
              <span>04</span>
              <p>Correções preservam a versão anterior e deixam rastro público.</p>
            </div>
          </div>
        </div>
      </section>

      <footer>
        <div className="footer-inner">
          <div>
            <a className="brand brand-footer" href="#inicio">
              <BrandMark />
              <span>Barreiras em Dados</span>
            </a>
            <p>
              Civic tech independente para tornar a informação pública de
              Barreiras mais acessível e verificável.
            </p>
          </div>

          <div className="footer-status">
            <span className="status-dot" />
            Pré-lançamento — dados cívicos ainda não publicados
          </div>
        </div>
      </footer>
    </main>
  );
}
