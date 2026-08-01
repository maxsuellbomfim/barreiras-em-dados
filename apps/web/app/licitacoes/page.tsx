import type { Metadata } from "next";

import {
  getPncpProcurements,
  type Procurement,
} from "../../lib/pncp-procurements";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Licitações e contratações",
  description:
    "Contratações públicas de Barreiras registradas no PNCP: objeto, " +
    "valores oficiais e quem venceu cada item, com fonte verificável.",
};

const BARREIRAS_CNPJ = "13654405000195";

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string) {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

function pncpUrl(procurement: Procurement) {
  return (
    "https://pncp.gov.br/app/editais/" +
    `${BARREIRAS_CNPJ}/${procurement.ano}/${procurement.sequencial}`
  );
}

function ProcurementCard({
  procurement,
}: Readonly<{ procurement: Procurement }>) {
  return (
    <article className="digest-card" aria-label="Contratação pública">
      <div className="track-top">
        <span>
          {procurement.modalidade ?? "Contratação"} ·{" "}
          {procurement.dataPublicacao
            ? formatDate(procurement.dataPublicacao)
            : `${procurement.ano}`}
        </span>
        <span className="track-status">
          {procurement.situacao ?? "situação no PNCP"}
        </span>
      </div>
      <h2 className="procurement-object">{procurement.objeto}</h2>
      <dl className="procurement-values">
        {procurement.unidade ? (
          <div>
            <dt>Unidade compradora</dt>
            <dd>{procurement.unidade}</dd>
          </div>
        ) : null}
        <div>
          <dt>Valor estimado (PNCP)</dt>
          <dd>
            {procurement.valorEstimado !== null
              ? currencyFormatter.format(procurement.valorEstimado)
              : "não informado"}
          </dd>
        </div>
        <div>
          <dt>Valor homologado (PNCP)</dt>
          <dd>
            {procurement.valorHomologado !== null
              ? currencyFormatter.format(procurement.valorHomologado)
              : "ainda sem homologação registrada"}
          </dd>
        </div>
      </dl>
      {procurement.resultados.length > 0 ? (
        <details className="procurement-results" open>
          <summary>
            Quem venceu ({procurement.resultados.length}{" "}
            {procurement.resultados.length === 1 ? "item" : "itens"})
          </summary>
          <ul>
            {procurement.resultados.map((resultado) => (
              <li key={`${procurement.controlNumber}-${resultado.numeroItem}`}>
                <strong>{resultado.fornecedor}</strong>
                {resultado.niFornecedor
                  ? ` · CNPJ ${resultado.niFornecedor}`
                  : resultado.tipoPessoa === "PF"
                    ? " · pessoa física (documento preservado)"
                    : ""}
                {resultado.valorTotalHomologado !== null
                  ? ` — ${currencyFormatter.format(
                      resultado.valorTotalHomologado,
                    )}`
                  : ""}
                {resultado.dataResultado
                  ? ` (homologado em ${formatDate(resultado.dataResultado)})`
                  : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="meta-note">
          Nenhum resultado homologado registrado até agora para esta
          contratação.
        </p>
      )}
      <p className="act-evidence">
        <a href={pncpUrl(procurement)} target="_blank" rel="noreferrer">
          Ver no PNCP (registro oficial)
        </a>{" "}
        · processo {procurement.controlNumber}
      </p>
      <p className="act-review-mode">
        Dados oficiais do Portal Nacional de Contratações Públicas, exibidos
        sem tratamento editorial. Valores estimados e homologados são os
        informados pelo próprio portal — nada é calculado por nós.
      </p>
    </article>
  );
}

export default async function ProcurementsPage() {
  const result = await getPncpProcurements();

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras em Dados">
            <span>← Barreiras em Dados</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário traduzido</a>
            <a href="/atos">Atos de pessoal</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="procurements-title">
        <div className="section-heading">
          <span className="eyebrow">Quem ganhou, por quanto</span>
          <h1 id="procurements-title">Licitações e contratações</h1>
          <p>
            As contratações de Barreiras registradas no Portal Nacional de
            Contratações Públicas (PNCP), com objeto, valores oficiais e o
            fornecedor vencedor de cada item homologado. Registro público
            espelhado da fonte — não é avaliação sobre empresas ou pessoas.
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
        ) : result.procurements.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>As primeiras contratações estão a caminho</strong>
              <p>
                A coleta automática no PNCP está ativa (janela semanal e
                backfill até julho de 2021). Os registros aparecerão aqui
                conforme forem preservados.
              </p>
            </div>
          </div>
        ) : (
          <div className="digest-grid">
            {result.procurements.map((procurement) => (
              <ProcurementCard
                key={procurement.controlNumber}
                procurement={procurement}
              />
            ))}
          </div>
        )}

        <p className="hero-note">
          Metodologia: espelho fiel dos registros do PNCP, preservados como
          bruto verificável por hash antes de qualquer exibição. CPF de
          pessoa física nunca é exposto. Encontrou um erro?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/licitacoes&labels=correcao"
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
            Valores oficiais do PNCP, sem cálculos próprios
          </div>
        </div>
      </footer>
    </main>
  );
}
