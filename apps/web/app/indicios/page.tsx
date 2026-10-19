import type { Metadata } from "next";

import { formatCnpj, getPublicIndicios, type Indicio } from "../../lib/indicios.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Indícios para apuração",
  description:
    "Padrões em contratos e gastos públicos de Barreiras que merecem apuração, com a regra, o documento oficial e a revisão registrada. Indício não é prova de irregularidade.",
};

const CORRECTION_URL =
  "https://github.com/maxsuellbomfim/barreiras-em-dados/issues/new?title=Contestação%20em%20/indicios&labels=correcao";

function formatDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

function IndicioCard({ item }: Readonly<{ item: Indicio }>) {
  return (
    <article className="digest-card finance-signal-card">
      <div className="track-top">
        <span>{item.ruleName}</span>
        <span className="finance-signal-badge finance-signal-medium">Indício</span>
      </div>
      <h3 className="procurement-object">
        {item.supplierName}
        <span className="meta"> · CNPJ {formatCnpj(item.supplierCnpj)}</span>
      </h3>
      <dl className="finance-details-list">
        <div>
          <dt>Empresa aberta em</dt>
          <dd>{formatDate(item.openedOn)} (cadastro da Receita Federal)</dd>
        </div>
        <div>
          <dt>Contrato</dt>
          <dd>
            nº {item.contractNumber}, início em {formatDate(item.contractStart)} —{" "}
            <strong>{item.daysAfterOpening} dias</strong> depois da abertura
          </dd>
        </div>
        <div>
          <dt>Valor inicial</dt>
          <dd>
            {formatBrlDecimal(item.contractValue)}
            {item.amendmentsValue && item.amendmentsValue !== "0.00" ? (
              <span className="meta"> · aditivos: {formatBrlDecimal(item.amendmentsValue)}</span>
            ) : null}
          </dd>
        </div>
        {item.contractObject ? (
          <div>
            <dt>Objeto</dt>
            <dd>{item.contractObject}</dd>
          </div>
        ) : null}
      </dl>
      <p className="finance-signal-explanation">{item.publicExplanation}</p>
      <details className="finance-details">
        <summary>Por que este caso foi publicado</summary>
        <p className="finance-details-note">{item.reviewRationale}</p>
        <p className="finance-details-note">
          {item.reviewKind === "automated" ? (
            <strong>Conferido automaticamente — sem revisão humana</strong>
          ) : (
            <strong>Revisão humana registrada</strong>
          )}{" "}
          em {formatDate(item.reviewedAt)}. Regra versionada <code>{item.ruleMethodology}</code>:{" "}
          {item.ruleDescription}
        </p>
        <p className="act-evidence">
          {item.contractSourceUrl ? (
            <>
              <a href={item.contractSourceUrl} target="_blank" rel="noreferrer">
                Ver contrato no Portal da Transparência
              </a>{" "}
              ·{" "}
            </>
          ) : null}
          hash do registro do contrato {item.contractArtifactSha256.slice(0, 12)}… · hash do
          cadastro da Receita {item.registryArtifactSha256.slice(0, 12)}…
        </p>
      </details>
    </article>
  );
}

export default async function IndiciosPage() {
  const result = await getPublicIndicios();

  return (
    <main>
      <section className="section" aria-labelledby="indicios-title">
        <div className="section-heading">
          <span className="eyebrow">Para quem quer fiscalizar</span>
          <h1 id="indicios-title">Indícios para apuração</h1>
          <p>
            Regras automáticas cruzam contratos, pagamentos e cadastros oficiais e apontam padrões
            que merecem apuração. Cada caso mostra o fato, a regra, o documento oficial e a
            revisão que o aprovou. <strong>Indício não é prova</strong>: não afirma que houve
            fraude, corrupção ou irregularidade, e quase sempre existe uma explicação possível
            que só a apuração confirma ou descarta.
          </p>
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <div>
              <strong>Indícios temporariamente indisponíveis</strong>
              <p>A falha é de consulta; ela não significa que não haja indícios.</p>
            </div>
          </div>
        ) : result.items.length === 0 ? (
          <article className="digest-card finance-signal-card">
            <strong>Nenhum indício aprovado no momento</strong>
            <p className="finance-signal-explanation">
              As regras rodam todos os dias; casos conferidos e rejeitados ficam registrados, com
              o motivo, e não aparecem aqui.
            </p>
          </article>
        ) : (
          <div className="digest-grid">
            {result.items.map((item) => (
              <IndicioCard item={item} key={item.findingId} />
            ))}
          </div>
        )}

        <h2>O que foi verificado e não encontrou caso</h2>
        <ul className="hero-note">
          <li>
            Pagamento a fornecedor com sanção que proíbe contratar com Barreiras (CEIS/CNEP,
            pagamentos de 2024 a 2026): nenhum.
          </li>
          <li>
            Compra direta fracionada (dispensas do PNCP de 2024 a 2026 somadas por objeto): nenhuma.
          </li>
          <li>
            Mesma fonte publicando demonstrativos de despesa diferentes para o mesmo mês: nenhum.
          </li>
          <li>
            Licitação com um único concorrente: ainda não verificada; o PNCP não informa os
            participantes.
          </li>
        </ul>

        <p className="hero-note">
          Como funciona: cada regra é determinística e versionada, medida em produção antes de ir
          ao ar. Cada caso passa por duas conferências registradas — por código, contra o registro
          oficial preservado, e por um agente de IA que procura erro de dado e explicação lícita
          comum (por exemplo, credenciamento aberto a todos os habilitados) e pode vetar. Casos
          rejeitados não aparecem. Nomes de pessoas físicas não são publicados.
        </p>
        <p className="hero-note">
          Encontrou um erro ou tem uma explicação para um caso?{" "}
          <a href={CORRECTION_URL} target="_blank" rel="noreferrer">
            Conteste
          </a>
          . A contestação faz o caso ser conferido de novo; se a evidência não se sustentar, ele
          sai do ar e a correção fica registrada.
        </p>
      </section>
    </main>
  );
}
