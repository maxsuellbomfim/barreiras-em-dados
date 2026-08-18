import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sobre o projeto",
  description:
    "O que é o Barreiras 360, como os dados são coletados e revisados, e como contestar qualquer registro publicado.",
  openGraph: {
    title: "Sobre o Barreiras 360",
    description:
      "Plataforma cívica apartidária: fonte oficial, hash e revisão em cada registro — e um canal público para contestar qualquer dado.",
  },
};

const REPOSITORY_URL = "https://github.com/maxsuellbomfim/barreiras-em-dados";

export default function AboutPage() {
  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/financas">Finanças</a>
            <a href="/recursos">Recursos</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="about-title">
        <div className="section-heading">
          <span className="eyebrow">Transparência sobre a transparência</span>
          <h1 id="about-title">O que é o Barreiras 360</h1>
          <p>
            Uma plataforma cívica, apartidária e verificável sobre Barreiras.
            Ela existe para que qualquer pessoa acompanhe o dinheiro público, as
            decisões e os representantes da cidade — com o documento oficial ao
            lado de cada informação.
          </p>
        </div>

        <aside className="transfer-reading-guide">
          <strong>O que este site não é</strong>
          <p>
            Não é um site de campanha, não apoia nem ataca candidatos e não
            publica opinião. Nenhum registro é uma acusação: sinais estatísticos
            e valores oficiais são apresentados com contexto e nunca viram
            julgamento automático. Ausência de dado é sempre declarada como
            ausência — nunca convertida em zero, elogio ou defeito.
          </p>
        </aside>

        <div className="section-heading">
          <h2>Como um dado chega até aqui</h2>
          <p>
            Todo registro percorre o mesmo caminho, sempre nessa ordem:
          </p>
        </div>
        <ol className="transfer-card-list">
          <li className="transfer-card">
            <strong>1 · Coleta na fonte oficial.</strong> Robôs de código
            aberto baixam diários, APIs e arquivos públicos do governo — nunca
            conteúdo de redes sociais ou de terceiros.
          </li>
          <li className="transfer-card">
            <strong>2 · Preservação imutável.</strong> O arquivo original é
            guardado com uma impressão digital criptográfica (SHA-256). Se a
            fonte mudar depois, dá para provar o que estava publicado.
          </li>
          <li className="transfer-card">
            <strong>3 · Extração determinística.</strong> Números e nomes são
            extraídos por código reproduzível. Inteligência artificial nunca
            calcula totais e nunca decide o que é publicado.
          </li>
          <li className="transfer-card">
            <strong>4 · Revisão humana.</strong> Conteúdo interpretativo só é
            publicado depois de revisão registrada. Registros literais de atos
            oficiais seguem regra própria, com verificação por código e
            reversão auditada.
          </li>
          <li className="transfer-card">
            <strong>5 · Publicação com evidência.</strong> Cada tela mostra a
            fonte, a data da coleta e o caminho até o documento original.
          </li>
        </ol>

        <div className="section-heading">
          <h2>Encontrou um erro? Conteste.</h2>
          <p>
            Qualquer pessoa pode contestar qualquer registro — inclusive quem é
            citado nele. Correções geram uma nova versão pública; o histórico
            nunca é apagado em silêncio.
          </p>
        </div>
        <p>
          O código-fonte, as decisões de arquitetura e o registro de mudanças
          são públicos e auditáveis:{" "}
          <a href={REPOSITORY_URL} rel="noreferrer" target="_blank">
            repositório oficial do projeto ↗
          </a>
          . Para contestar um dado, abra um relato público no repositório
          apontando a página e o documento oficial que sustenta a correção.
        </p>

        <details className="transfer-methodology">
          <summary>De onde vêm os dados</summary>
          <p>
            Diário Oficial de Barreiras, portais de transparência da Prefeitura
            e da Câmara Municipal, Portal Nacional de Contratações Públicas
            (PNCP), Transferegov, Portal da Transparência do Governo Federal
            (CGU), Diário e LOA do Estado da Bahia, Câmara dos Deputados,
            Assembleia Legislativa da Bahia e Tribunal Superior Eleitoral. A
            lista completa, com o estado de cada coleta, está documentada no
            repositório público.
          </p>
        </details>
      </section>
    </main>
  );
}
