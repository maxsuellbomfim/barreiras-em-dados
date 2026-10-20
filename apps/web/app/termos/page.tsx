import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Termos de uso",
  description: "Como usar e reutilizar as informações do Barreiras 360 e quais são os limites delas.",
};

export default function TermsPage() {
  return (
    <main>
      <section className="section legal-text" aria-labelledby="terms-title">
        <div className="section-heading">
          <span className="eyebrow">Transparência da própria plataforma</span>
          <h1 id="terms-title">Termos de uso</h1>
          <p>
            O Barreiras 360 é gratuito, não exige cadastro e pode ser usado por qualquer pessoa.
            Ao usar o site, considere os limites abaixo.
          </p>
        </div>

        <h2>Natureza da informação</h2>
        <ul>
          <li>
            O site reorganiza registros oficiais e mostra a fonte de cada um. Em caso de
            divergência, vale o documento oficial.
          </li>
          <li>
            Totais e comparações são calculados por regras determinísticas e versionadas, descritas
            em cada página. Cobertura incompleta é informada; período sem dado não significa zero.
          </li>
          <li>
            <strong>Indício não é prova.</strong> A página de <a href="/indicios">indícios</a>{" "}
            aponta padrões que merecem apuração. Ela não afirma que houve crime, fraude, corrupção
            ou irregularidade, e não substitui a investigação dos órgãos de controle.
          </li>
          <li>
            Parte das conferências é feita automaticamente por programas e por agentes de IA; isso
            é informado junto de cada conteúdo (&quot;conferido automaticamente — sem revisão
            humana&quot;).
          </li>
        </ul>

        <h2>Reutilização</h2>
        <p>
          Os dados são públicos e podem ser reutilizados, citando a fonte oficial e o Barreiras
          360. Ao reutilizar, mantenha o contexto: não apresente um indício como acusação nem um
          dado parcial como completo.
        </p>

        <h2>Uso vedado</h2>
        <ul>
          <li>Usar o site para ameaçar, assediar ou expor pessoas.</li>
          <li>Enviar contestações falsas, em massa ou com dados pessoais de terceiros.</li>
          <li>Tentar sobrecarregar ou burlar os sistemas do site.</li>
        </ul>

        <h2>Erros e correções</h2>
        <p>
          Erros podem acontecer na fonte ou no processamento. Use o{" "}
          <a href="/contestar">formulário de contestação</a> para pedir correção; ele é anônimo e
          gera protocolo. Correções criam nova versão e ficam registradas.
        </p>

        <h2>Neutralidade</h2>
        <p>
          A mesma metodologia vale para todos os órgãos, gestões, partidos e fornecedores. O site
          não faz campanha, não recomenda voto e não ordena conteúdo por partido.
        </p>
      </section>
    </main>
  );
}
