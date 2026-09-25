import type { Metadata } from "next";

import {
  getApprovedGazetteActs,
} from "../../lib/approved-acts";
import { ActExplorer } from "./act-explorer";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Atos públicos",
  description:
    "Atos públicos do Diário Oficial de Barreiras, com busca, resumo assistido " +
    "e ligação verificável ao documento oficial.",
  openGraph: {
    title: "Nomeações e exonerações em Barreiras",
    description:
      "Quem entrou e quem saiu da Prefeitura, com o trecho literal do Diário Oficial em cada registro.",
  },
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

      <section className="section" aria-labelledby="acts-title">
        <div className="section-heading">
          <span className="eyebrow">Linha do tempo oficial, ligada à fonte</span>
          <h1 id="acts-title">Atos públicos</h1>
          <p>
            Quem foi nomeado ou exonerado na Prefeitura, com o trecho do Diário
            Oficial que comprova cada ato. É um registro de atos, não uma
            avaliação sobre pessoas.
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
                A coleta e a validação determinística continuam em andamento.
                Registros podem ser publicados automaticamente quando o código
                confirma o trecho oficial; casos ambíguos ficam para revisão.
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

    </main>
  );
}
