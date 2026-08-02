import type { Metadata } from "next";

import {
  getPncpProcurements,
} from "../../lib/pncp-procurements";
import { ProcurementExplorer } from "./procurement-explorer";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Licitações e contratações",
  description:
    "Contratações públicas de Barreiras registradas no PNCP: objeto, " +
    "valores oficiais e quem venceu cada item, com fonte verificável.",
};

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
          <ProcurementExplorer procurements={result.procurements} />
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
