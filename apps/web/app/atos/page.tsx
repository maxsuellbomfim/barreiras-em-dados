import type { Metadata } from "next";

import {
  getApprovedGazetteActs,
} from "../../lib/approved-acts";
import { ActExplorer } from "./act-explorer";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Nomeações e exonerações",
  description:
    "Atos de pessoal do Diário Oficial de Barreiras, revisados por uma " +
    "pessoa e ligados ao documento oficial que os sustenta.",
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Bahia",
});

export default async function ApprovedActsPage() {
  const result = await getApprovedGazetteActs();

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras em Dados">
            <span>← Barreiras em Dados</span>
          </a>
        </div>
      </header>

      <section className="section" aria-labelledby="acts-title">
        <div className="section-heading">
          <span className="eyebrow">Revisado por gente, ligado à fonte</span>
          <h1 id="acts-title">Nomeações e exonerações</h1>
          <p>
            Cada registro abaixo foi identificado automaticamente no Diário
            Oficial, conferido por uma pessoa e publicado com o trecho e o
            documento que o sustentam. Isto é um registro de atos oficiais —
            não é avaliação sobre pessoas.
          </p>
          {result.state === "available" && result.acts.length > 0 ? (
            <p className="acts-count" role="status">
              {result.acts.length.toLocaleString("pt-BR")}{" "}
              {result.acts.length === 1 ? "ato publicado" : "atos publicados"}{" "}
              · última publicação em{" "}
              {dateTimeFormatter.format(
                new Date(
                  result.acts
                    .map((act) => act.approvedAt)
                    .sort()
                    .at(-1) as string,
                ),
              )}
            </p>
          ) : null}
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
        ) : result.acts.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Nenhum ato publicado até agora</strong>
              <p>
                A coleta e a revisão humana estão em andamento. Os primeiros
                atos aprovados aparecerão aqui — nunca antes de uma pessoa
                conferir cada um.
              </p>
            </div>
          </div>
        ) : (
          <ActExplorer acts={result.acts} />
        )}

        <p className="hero-note">
          Metodologia: identificação determinística e versionada, revisão
          humana registrada e evidência por hash SHA-256. Correções criam
          novas versões, sem apagar o histórico.
        </p>

        <p className="hero-note">
          Encontrou um erro ou uma informação desatualizada?{" "}
          <a
            href="https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Correção%20em%20/atos&labels=correcao"
            target="_blank"
            rel="noreferrer"
          >
            Abra um pedido público de correção
          </a>
          . Todo relato e toda resposta ficam registrados publicamente.
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
            Atos publicados somente após revisão humana registrada
          </div>
        </div>
      </footer>
    </main>
  );
}
