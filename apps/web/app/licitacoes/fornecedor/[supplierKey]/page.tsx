import type { Metadata } from "next";

import { formatBrlDecimal } from "../../../../lib/revenues";
import { getPublicSupplierHistory } from "../../../../lib/supplier-history";
import {
  getPublicSupplierSanctions,
  type SupplierSanctionsResult,
} from "../../../../lib/supplier-sanctions";
import { SupplierSanctionCard } from "../../supplier-sanction-card";

const CNPJ_KEY = /^\d{14}$/;

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Histórico do fornecedor | Barreiras 360",
  description: "Processos e resultados PNCP associados a um fornecedor público.",
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string | null): string {
  if (!value) return "data não informada";
  const parsed = new Date(`${value}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

type SupplierHistoryPageProps = {
  params: Promise<{ supplierKey: string }>;
};

function SupplierSanctionSection({
  cnpj,
  result,
}: Readonly<{ cnpj: string; result: SupplierSanctionsResult }>) {
  const matched =
    result.state === "available"
      ? result.sanctions.filter((sanction) => sanction.supplierCnpj === cnpj)
      : [];
  return (
    <section
      className="finance-documents"
      aria-labelledby="supplier-sanctions-title"
    >
      <div className="section-heading compact">
        <span className="eyebrow">Cadastros federais de sanções</span>
        <h2 id="supplier-sanctions-title">Este CNPJ no CEIS e no CNEP</h2>
        <p>
          Conferência do CNPJ deste fornecedor nos cadastros federais de
          empresas sancionadas (CEIS e CNEP), mantidos pela CGU. O resultado é
          um espelho literal do cadastro na data da consulta — não uma
          avaliação nossa.
        </p>
      </div>
      {result.state === "unavailable" ? (
        <div className="collection-unavailable" role="status">
          <strong>Consulta aos cadastros temporariamente indisponível</strong>
          <p>
            Isso representa uma falha de consulta, não ausência ou existência
            de sanção.
          </p>
        </div>
      ) : matched.length === 0 ? (
        <p className="act-review-mode">
          Nenhum registro para este CNPJ no espelho mais recente dos cadastros
          CEIS e CNEP. Isso reflete a última consulta preservada, não uma
          certidão negativa.
        </p>
      ) : (
        <div className="digest-grid">
          {matched.map((sanction) => (
            <SupplierSanctionCard
              key={`${sanction.registry}-${sanction.sanctionId}`}
              sanction={sanction}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default async function SupplierHistoryPage({ params }: SupplierHistoryPageProps) {
  const { supplierKey } = await params;
  const decodedKey = decodeURIComponent(supplierKey);
  const isCnpjKey = CNPJ_KEY.test(decodedKey);
  // ponytail: a RPC de sanções não filtra por CNPJ; com ~60 sanções hoje,
  // filtrar as 200 primeiras no servidor basta. Criar filtro SQL se o
  // espelho crescer além da página única.
  const [result, sanctionsResult] = await Promise.all([
    getPublicSupplierHistory(decodedKey),
    isCnpjKey
      ? getPublicSupplierSanctions()
      : Promise.resolve<SupplierSanctionsResult>({ state: "unavailable" }),
  ]);
  const supplierName = result.state === "available" ? result.rows[0]?.supplierName : null;

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/licitacoes" aria-label="Voltar para licitações">
            <span>← Licitações</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/financas">Finanças</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section" aria-labelledby="supplier-history-title">
        <div className="section-heading">
          <span className="eyebrow">Histórico PNCP</span>
          <h1 id="supplier-history-title">{supplierName ?? "Fornecedor"}</h1>
          <p>
            Processos e resultados homologados preservados para este fornecedor. Esta página
            ajuda a acompanhar recorrência ao longo do tempo; não é avaliação de legalidade ou desempenho.
          </p>
        </div>

        {result.state === "unavailable" ? (
          <div className="collection-unavailable" role="status">
            <strong>Histórico temporariamente indisponível</strong>
            <p>Isso representa uma falha de consulta, não ausência de dados.</p>
          </div>
        ) : result.rows.length === 0 ? (
          <div className="collection-unavailable" role="status">
            <strong>Nenhum processo encontrado</strong>
            <p>Não há resultado homologado preservado para este identificador.</p>
          </div>
        ) : (
          <div className="supplier-history-list">
            {result.rows.map((row) => (
              <article className="supplier-history-card" key={row.controlNumber}>
                <div className="track-top">
                  <span>Processo {row.controlNumber}</span>
                  <span className="track-status">{row.itemCount.toLocaleString("pt-BR")} itens</span>
                </div>
                <h2>{row.objectDescription}</h2>
                <dl className="supplier-history-values">
                  <div><dt>Valor homologado</dt><dd>{formatBrlDecimal(row.totalAwardedAmount)}</dd></div>
                  <div><dt>Publicação</dt><dd>{formatDate(row.publicationDate)}</dd></div>
                  <div><dt>Resultado</dt><dd>{formatDate(row.resultDate)}</dd></div>
                </dl>
                {row.sourceUrl ? (
                  <p className="act-evidence"><a href={row.sourceUrl} target="_blank" rel="noreferrer">Ver registro oficial do PNCP</a></p>
                ) : null}
              </article>
            ))}
          </div>
        )}

        {isCnpjKey ? (
          <SupplierSanctionSection cnpj={decodedKey} result={sanctionsResult} />
        ) : null}

        <p className="hero-note">
          Metodologia: resultados deduplicados por compra, item e sequência; valores são os informados pelo PNCP.
          A ausência de recorrência nesta página não prova ausência em fontes ainda não coletadas.
        </p>
      </section>
    </main>
  );
}
