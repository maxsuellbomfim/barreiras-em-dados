import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Aviso de privacidade",
  description:
    "Quais dados o Barreiras 360 trata, de onde vêm, o que não é publicado e como pedir correção.",
};

export default function PrivacyPage() {
  return (
    <main>
      <section className="section legal-text" aria-labelledby="privacy-title">
        <div className="section-heading">
          <span className="eyebrow">Transparência da própria plataforma</span>
          <h1 id="privacy-title">Aviso de privacidade</h1>
          <p>
            O Barreiras 360 organiza informação pública sobre a gestão do município de Barreiras
            (BA). Este aviso explica quais dados pessoais aparecem no site, por quê, o que fica de
            fora e como pedir correção.
          </p>
        </div>

        <h2>De onde vêm os dados</h2>
        <p>
          Só de fontes oficiais de acesso público: Diário Oficial do Município, portais de
          transparência da Prefeitura e da Câmara, Tribunal de Contas dos Municípios da Bahia,
          Portal Nacional de Contratações Públicas, Portal da Transparência e cadastros da
          Controladoria-Geral da União, Receita Federal, Tesouro Nacional (SICONFI), Tribunal
          Superior Eleitoral, Transferegov e órgãos estaduais. Cada informação mostra a fonte e o
          documento de origem. O tratamento segue a finalidade pública que justificou a
          divulgação desses dados (Lei de Acesso à Informação e Lei Geral de Proteção de Dados,
          art. 7º, § 3º): permitir que qualquer pessoa acompanhe o uso do dinheiro público.
        </p>

        <h2>Que dados pessoais aparecem</h2>
        <ul>
          <li>
            Agentes públicos no exercício da função: nome, cargo, órgão e atos publicados
            (nomeações, exonerações, mandatos, votos e autorias).
          </li>
          <li>
            Fornecedores e beneficiários de pagamentos públicos: razão social e CNPJ de empresas.
            Pessoas físicas contratadas pelo poder público aparecem pelo nome, como na fonte
            oficial (contratos e empenhos), nunca com CPF; algumas páginas as mostram só somadas
            por órgão.
          </li>
          <li>Candidatos e eleitos: dados divulgados pela Justiça Eleitoral.</li>
        </ul>

        <h2>O que não é publicado</h2>
        <ul>
          <li>CPF completo, inclusive o que aparece no texto do Diário Oficial (fica mascarado).</li>
          <li>Descontos pessoais de servidores, como pensão alimentícia ou consignados.</li>
          <li>Nome de pessoa física associado a um indício.</li>
          <li>Dados sensíveis (saúde, religião, filiação sindical) que não sejam necessários.</li>
        </ul>

        <h2>Dados de quem usa o site</h2>
        <p>
          O site não usa cookies de rastreamento, não tem anúncios e não exige cadastro. Quem
          envia uma <a href="/contestar">contestação</a> não precisa se identificar; o texto e o
          contato opcional ficam guardados só para analisar o pedido, não são publicados e não são
          compartilhados. A hospedagem pode registrar dados técnicos de acesso (como endereço IP)
          por motivo de segurança, conforme a política do provedor.
        </p>

        <h2>Correção e atualização</h2>
        <p>
          Qualquer pessoa, inclusive quem é citado, pode pedir correção ou registrar resposta pelo{" "}
          <a href="/contestar">formulário de contestação</a>, sem login. O pedido recebe protocolo
          e faz a informação ser conferida de novo contra a fonte oficial. Correções criam nova
          versão; o histórico é preservado.
        </p>

        <h2>Responsabilidade</h2>
        <p>
          O Barreiras 360 é uma iniciativa cívica independente, sem vínculo com partidos ou com a
          administração municipal. O canal de contato para qualquer assunto de privacidade é o{" "}
          <a href="/contestar">formulário de contestação</a>.
        </p>
      </section>
    </main>
  );
}
