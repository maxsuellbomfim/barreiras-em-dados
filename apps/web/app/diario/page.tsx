import type { Metadata } from "next";

import {
  getEditionDigests,
  type DigestItem,
  type EditionDigest,
} from "../../lib/edition-digests";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Diário Oficial traduzido",
  description:
    "Cada edição do Diário Oficial de Barreiras resumida em linguagem " +
    "simples, com citação literal do texto oficial em cada item.",
};

const TYPE_LABELS: Readonly<Record<string, string>> = {
  nomeacao: "Nomeação",
  exoneracao: "Exoneração",
  contrato: "Contrato",
  licitacao: "Licitação",
  decreto: "Decreto",
  portaria: "Portaria",
  aviso: "Aviso",
  outro: "Outros",
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

function ItemRow({ item }: Readonly<{ item: DigestItem }>) {
  return (
    <li className="digest-item">
      <span className="digest-item-type">
        {TYPE_LABELS[item.tipo] ?? "Outros"}
      </span>
      <div>
        <h3>{item.titulo}</h3>
        <details className="digest-item-explanation">
          <summary>Explicação em palavras simples</summary>
          <p>{item.resumo}</p>
        </details>
        <details>
          <summary>Citação do texto oficial</summary>
          <pre className="act-excerpt">“{item.trecho}”</pre>
        </details>
      </div>
    </li>
  );
}

function DigestCard({ digest }: Readonly<{ digest: EditionDigest }>) {
  return (
    <article className="digest-card" aria-label="Resumo de edição">
      <div className="track-top">
        <span>
          Edição {digest.edition.toLocaleString("pt-BR")}/
          {digest.editionYear}
        </span>
        <span className="track-status">
          {digest.editionDate
            ? `Publicada em ${new Intl.DateTimeFormat("pt-BR", {
                day: "2-digit",
                month: "short",
                year: "numeric",
                timeZone: "America/Bahia",
              }).format(new Date(`${digest.editionDate}T12:00:00-03:00`))}`
            : "Data da edição não informada"}
        </span>
      </div>
      <p className="digest-card-meta">
        {digest.items.length} {digest.items.length === 1 ? "item" : "itens"}
        {digest.partial ? " · resumo parcial" : ""}
      </p>
      <ul className="digest-items">
        {digest.items.map((item, index) => (
          <ItemRow key={`${digest.digestId}-${index}`} item={item} />
        ))}
      </ul>
      <p className="act-evidence">
        {digest.gazetteUrl ? (
          <a href={digest.gazetteUrl} target="_blank" rel="noreferrer">
            Ver a edição oficial (PDF)
          </a>
        ) : (
          <span>Edição preservada no acervo verificável</span>
        )}{" "}
        · hash {digest.artifactSha256.slice(0, 12)}… · publicado em{" "}
        {dateTimeFormatter.format(new Date(digest.publishedAt))}
      </p>
      <p className="act-review-mode">
        Resumo gerado com IA e verificado por código: cada item traz uma
        citação literal conferida no texto oficial; itens sem citação são
        descartados. Sujeito a correção — e toda correção fica registrada.
      </p>
    </article>
  );
}

export default async function EditionDigestsPage() {
  const result = await getEditionDigests();

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/atos">Atos públicos</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="digests-title">
        <div className="section-heading">
          <span className="eyebrow">O Diário inteiro, em palavras simples</span>
          <h1 id="digests-title">Diário Oficial traduzido</h1>
          <p>
            Cada edição resumida item a item — nomeações, contratos,
            licitações, decretos e avisos — em linguagem que qualquer pessoa
            entende. Todo item carrega uma citação literal do texto oficial,
            conferida por código antes de publicar. Isto é um espelho
            traduzido do registro oficial, não uma avaliação.
          </p>
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Resumos temporariamente indisponíveis</strong>
              <p>
                Isso representa uma falha de consulta, não ausência de dados.
                Tente novamente em alguns minutos.
              </p>
            </div>
          </div>
        ) : result.digests.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Os primeiros resumos estão a caminho</strong>
              <p>
                As edições já estão preservadas no acervo; os resumos são
                gerados e verificados automaticamente a cada coleta e
                aparecerão aqui em breve.
              </p>
            </div>
          </div>
        ) : (
          <div className="digest-grid">
            {result.digests.map((digest) => (
              <DigestCard key={digest.digestId} digest={digest} />
            ))}
          </div>
        )}

        <p className="hero-note">
          Metodologia: resumo assistido por IA com âncora literal verificada
          por código versionado (ADR 0013); publicação automática auditada e
          reversível. Encontrou um erro?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/diario&labels=correcao"
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
            Resumos ancorados no documento oficial, item a item
          </div>
        </div>
      </footer>
    </main>
  );
}
