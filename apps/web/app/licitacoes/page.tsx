import type { Metadata } from "next";

import {
  getPncpProcurements,
  type ProcurementFilters,
} from "../../lib/pncp-procurements";
import {
  getPublicSupplierConcentration,
  type PublicSupplierConcentration,
} from "../../lib/supplier-concentration";
import { formatBrlDecimal } from "../../lib/revenues";
import { ProcurementExplorer } from "./procurement-explorer";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Licitações e contratações",
  description:
    "Contratações públicas de Barreiras registradas no PNCP: objeto, " +
    "valores oficiais e quem venceu cada item, com fonte verificável.",
};

function formatShare(value: string): string {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? `${(numeric * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
    : "não calculado";
}

function cleanFilter(value: string | undefined, maxLength: number): string | undefined {
  const normalized = value?.trim();
  return normalized && normalized.length <= maxLength ? normalized : undefined;
}

function parseYear(value: string | undefined): number | undefined {
  if (!value || !/^\d{4}$/.test(value)) return undefined;
  const year = Number(value);
  return year >= 1900 && year <= 2200 ? year : undefined;
}

function supplierSignalKind(supplier: PublicSupplierConcentration): "attention" | "monitoring" | "summary" {
  if (supplier.attentionSignal) return "attention";
  if (supplier.procurementCount === 1 && Number(supplier.awardedShare) >= 0.5) return "monitoring";
  return "summary";
}

function supplierSignalLabel(supplier: PublicSupplierConcentration): string {
  const kind = supplierSignalKind(supplier);
  if (kind === "attention") return "merece contexto";
  if (kind === "monitoring") return "acompanhar histórico";
  return "resumo";
}

type ProcurementsPageProps = {
  searchParams: Promise<{
    fornecedor?: string;
    ano?: string;
    q?: string;
  }>;
};

export default async function ProcurementsPage({ searchParams }: ProcurementsPageProps) {
  const params = await searchParams;
  const filters: ProcurementFilters = {
    supplierKey: cleanFilter(params.fornecedor, 200),
    fiscalYear: parseYear(params.ano),
    query: cleanFilter(params.q, 120),
  };
  const hasFilters = Boolean(filters.supplierKey || filters.fiscalYear || filters.query);
  const [result, supplierResult] = await Promise.all([
    getPncpProcurements(filters),
    hasFilters
      ? Promise.resolve({ state: "available" as const, suppliers: [] as const })
      : getPublicSupplierConcentration(),
  ]);

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/" aria-label="Barreiras 360">
            <span>← Barreiras 360</span>
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

        <form className="procurement-filter-form" method="get" aria-label="Filtrar contratações">
          <label>
            Fornecedor ou CNPJ
            <input name="fornecedor" defaultValue={filters.supplierKey ?? ""} placeholder="Ex.: 07665220000183" />
          </label>
          <label>
            Ano
            <input name="ano" inputMode="numeric" pattern="[0-9]{4}" defaultValue={filters.fiscalYear?.toString() ?? ""} placeholder="2026" />
          </label>
          <label className="procurement-filter-query">
            Palavra no objeto ou unidade
            <input name="q" defaultValue={filters.query ?? ""} placeholder="Ex.: infraestrutura" />
          </label>
          <div className="procurement-filter-actions">
            <button type="submit">Filtrar</button>
            {hasFilters ? <a className="button-secondary" href="/licitacoes">Limpar</a> : null}
          </div>
        </form>

        {hasFilters ? (
          <p className="procurement-filter-active" role="status">
            Filtros ativos. O resumo de fornecedores abaixo é substituído pela lista filtrada.
          </p>
        ) : null}

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
          <>
            {supplierResult.state === "available" && supplierResult.suppliers.length > 0 ? (
              <section className="supplier-concentration-section" aria-labelledby="supplier-concentration-title">
                <div className="section-heading compact">
                  <span className="eyebrow">Cruzamento PNCP</span>
                  <h2 id="supplier-concentration-title">Quem aparece nos resultados</h2>
                  <p>
                    Resumo dos fornecedores vencedores na janela preservada. “Merece contexto”
                    indica recorrência entre processos; não é ranking, julgamento ou prova de irregularidade.
                  </p>
                </div>
                <div className="supplier-concentration-grid">
                  {supplierResult.suppliers.map((supplier) => (
                    <article className="supplier-concentration-card" key={supplier.supplierKey}>
                      <div className="track-top">
                        <span>{supplier.supplierType === "PJ" ? "Pessoa jurídica" : "Fornecedor"}</span>
                        <span className={`supplier-signal-badge supplier-signal-${supplierSignalKind(supplier)}`}>
                          {supplierSignalLabel(supplier)}
                        </span>
                      </div>
                      <h3>{supplier.supplierName}</h3>
                      <dl className="supplier-concentration-values">
                        <div><dt>Processos</dt><dd>{supplier.procurementCount.toLocaleString("pt-BR")}</dd></div>
                        <div><dt>Itens</dt><dd>{supplier.itemCount.toLocaleString("pt-BR")}</dd></div>
                        <div><dt>Valor homologado</dt><dd>{formatBrlDecimal(supplier.totalAwardedAmount)}</dd></div>
                        <div><dt>Parcela da janela</dt><dd>{formatShare(supplier.awardedShare)}</dd></div>
                      </dl>
                      <p className="supplier-concentration-explanation">{supplier.publicExplanation}</p>
                      <p className="supplier-history-link">
                        <a href={`/licitacoes/fornecedor/${encodeURIComponent(supplier.supplierKey)}`}>
                          Ver histórico deste fornecedor →
                        </a>
                      </p>
                      {supplier.sourceUrl ? <p className="act-evidence"><a href={supplier.sourceUrl} target="_blank" rel="noreferrer">Ver fonte PNCP</a></p> : null}
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
            <ProcurementExplorer procurements={result.procurements} />
          </>
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
              <span>Barreiras 360</span>
            </a>
            <p>
              Informação pública de Barreiras para acompanhar a cidade com
              clareza.
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
