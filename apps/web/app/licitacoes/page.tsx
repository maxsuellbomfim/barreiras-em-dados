import type { Metadata } from "next";

import {
  getPncpProcurements,
  getPncpProcurementFilterOptions,
  type ProcurementFilters,
} from "../../lib/pncp-procurements";
import {
  getPublicSupplierConcentration,
  type PublicSupplierConcentration,
} from "../../lib/supplier-concentration";
import { formatBrlDecimal } from "../../lib/revenues";
import {
  getPublicMunicipalContracts,
  municipalSupplierLabel,
  type MunicipalContract,
} from "../../lib/municipal-contracts";
import {
  getPublicMunicipalProcurementProcesses,
  municipalCategoryLabel,
  municipalModalityLabel,
  municipalSourceCodeLabel,
  type MunicipalProcurementProcess,
} from "../../lib/municipal-procurement-processes";
import { getPublicSupplierSanctions } from "../../lib/supplier-sanctions";
import { ProcurementExplorer } from "./procurement-explorer";
import { SupplierSanctionCard } from "./supplier-sanction-card";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Licitações e contratações",
  description:
    "Contratações públicas de Barreiras registradas no PNCP: objeto, " +
    "valores oficiais e quem venceu cada item, com fonte verificável.",
  openGraph: {
    title: "O que Barreiras está comprando, e de quem",
    description:
      "Licitações e contratações registradas no PNCP, com valores oficiais e o vencedor de cada item.",
  },
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

function optionsFor(
  options: readonly {
    optionType: string;
    value: string;
    variantCount: number;
    procurementCount: number;
  }[],
  optionType: string,
) {
  return options.filter((option) => option.optionType === optionType).slice(0, 50);
}

function optionLabel(option: {
  value: string;
  procurementCount: number;
  variantCount?: number;
}): string {
  const variants = option.variantCount && option.variantCount > 1
    ? `, ${option.variantCount} variações de grafia`
    : "";
  return `${option.value} (${option.procurementCount}${variants})`;
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
    modalidade?: string;
    situacao?: string;
    orgao?: string;
  }>;
};

function SupplierSanctionsPanel({
  result,
}: Readonly<{
  result: Awaited<ReturnType<typeof getPublicSupplierSanctions>>;
}>) {
  return (
    <section className="finance-documents" aria-labelledby="supplier-sanctions-title">
      <div className="section-heading compact">
        <span className="eyebrow">Cadastros federais de sanções</span>
        <h2 id="supplier-sanctions-title">
          Fornecedores conferidos no CEIS e no CNEP
        </h2>
        <p>
          Cada CNPJ que aparece nas contratações publicadas de Barreiras é
          conferido nos cadastros federais de empresas sancionadas (CEIS e
          CNEP), mantidos pela CGU. O resultado é um espelho literal do
          cadastro — não uma avaliação nossa.
        </p>
      </div>
      {result.state === "unavailable" ? (
        <p className="transfer-empty">
          A conferência de sanções ainda não está disponível nesta consulta.
          Isso é limitação de coleta ou consulta, não um resultado.
        </p>
      ) : result.sanctions.length === 0 ? (
        <p className="transfer-empty">
          Na consulta mais recente, nenhum fornecedor verificado constava nos
          cadastros CEIS ou CNEP. Ausência de registro descreve a consulta na
          data em que foi feita; a conferência é refeita periodicamente.
        </p>
      ) : (
        <div className="digest-grid">
          {result.sanctions.map((sanction) => (
            <SupplierSanctionCard
              key={`${sanction.registry}:${sanction.sanctionId}`}
              sanction={sanction}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function MunicipalContractCard({
  contract,
}: Readonly<{ contract: MunicipalContract }>) {
  return (
    <article className="digest-card">
      <div className="track-top">
        <span>Contrato {contract.contractNumber}</span>
        <span className="track-status">
          {contract.validityStartText
            ? `vigência ${contract.validityStartText}${contract.validityEndText ? ` a ${contract.validityEndText}` : ""}`
            : "vigência não informada"}
        </span>
      </div>
      <h3 className="procurement-object">
        {contract.contractObject ?? "Objeto não informado no registro da fonte"}
      </h3>
      <dl className="procurement-values">
        <div>
          <dt>Contratado</dt>
          <dd>{contract.supplierName}</dd>
        </div>
        <div>
          <dt>Identificação</dt>
          <dd>{municipalSupplierLabel(contract)}</dd>
        </div>
        <div>
          <dt>Valor publicado pela fonte</dt>
          <dd>{contract.contractValueText ?? "não informado no registro"}</dd>
        </div>
        {contract.modalityCode ? (
          <div>
            <dt>Modalidade</dt>
            <dd>
              código {contract.modalityCode} (a fonte publica apenas o código)
            </dd>
          </div>
        ) : null}
      </dl>
      <p className="act-evidence">
        <a href={contract.documentUrl} target="_blank" rel="noreferrer">
          Abrir contrato oficial →
        </a>{" "}
        · resposta da API preservada · {contract.documentPreserved
          ? "PDF preservado"
          : "PDF ainda não preservado"}{" "}
        · hash {contract.artifactSha256.slice(0, 12)}…
      </p>
    </article>
  );
}

function MunicipalProcessCard({
  process,
}: Readonly<{ process: MunicipalProcurementProcess }>) {
  return (
    <article className="digest-card">
      <div className="track-top">
        <span>Processo {process.processNumber}</span>
        <span className="track-status">
          {process.publicationDateText
            ? `publicado em ${process.publicationDateText}`
            : "data de publicação não informada"}
        </span>
      </div>
      <h3 className="procurement-object">{process.processObject}</h3>
      <dl className="procurement-values">
        <div>
          <dt>Modalidade</dt>
          <dd>{municipalModalityLabel(process.modalityCode)}</dd>
        </div>
        <div>
          <dt>Categoria</dt>
          <dd>{municipalCategoryLabel(process.categoryCode)}</dd>
        </div>
        <div>
          <dt>Situação na fonte</dt>
          <dd>{municipalSourceCodeLabel(process.situationCode)}</dd>
        </div>
        <div>
          <dt>Resultado na fonte</dt>
          <dd>{municipalSourceCodeLabel(process.resultCode)}</dd>
        </div>
        <div>
          <dt>Valor estimado (texto da fonte)</dt>
          <dd>{process.estimatedValueText ?? "não informado"}</dd>
        </div>
        <div>
          <dt>Valor (texto da fonte)</dt>
          <dd>{process.awardedValueText ?? "não informado"}</dd>
        </div>
        {process.openingDateText ? (
          <div>
            <dt>Abertura</dt>
            <dd>{process.openingDateText}</dd>
          </div>
        ) : null}
        {process.noticeNumber ? (
          <div>
            <dt>Edital</dt>
            <dd>{process.noticeNumber}</dd>
          </div>
        ) : null}
      </dl>
      <p className="act-evidence">
        Resposta da API municipal preservada · hash{" "}
        {process.artifactSha256.slice(0, 12)}…
      </p>
    </article>
  );
}

function MunicipalProcessesPanel({
  result,
}: Readonly<{
  result: Awaited<ReturnType<typeof getPublicMunicipalProcurementProcesses>>;
}>) {
  return (
    <section
      className="finance-documents"
      aria-labelledby="municipal-processes-title"
    >
      <div className="section-heading compact">
        <span className="eyebrow">Portal municipal</span>
        <h2 id="municipal-processes-title">
          Processos licitatórios da Prefeitura
        </h2>
        <p>
          Espelho literal do portal de transparência municipal: objeto, datas e
          valores exatamente como publicados, sem conversão nem soma. Situação
          e resultado aparecem como códigos porque a fonte não publica a
          legenda; modalidade e categoria usam a legenda do próprio filtro do
          portal, sempre com o código ao lado.
        </p>
      </div>
      {result.state === "unavailable" ? (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Consulta aos processos temporariamente indisponível</strong>
            <p>
              Isso representa uma limitação de coleta ou consulta, não ausência
              de processos licitatórios.
            </p>
          </div>
        </div>
      ) : result.processes.length === 0 ? (
        <p className="act-review-mode">
          Nenhum processo preservado ainda nesta série. A coleta agendada
          preenche o acervo aos poucos.
        </p>
      ) : (
        <details className="finance-details">
          <summary>
            Ver os {result.processes.length.toLocaleString("pt-BR")} processos
            mais recentes
          </summary>
          <div className="digest-grid">
            {result.processes.map((process) => (
              <MunicipalProcessCard
                process={process}
                key={process.processRecordId}
              />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function MunicipalContractsPanel({
  result,
}: Readonly<{
  result: Awaited<ReturnType<typeof getPublicMunicipalContracts>>;
}>) {
  if (result.state === "unavailable" || result.contracts.length === 0) {
    return (
      <section className="finance-documents" aria-labelledby="municipal-contracts-title">
        <div className="section-heading compact">
          <span className="eyebrow">Portal municipal</span>
          <h2 id="municipal-contracts-title">Contratos da Prefeitura</h2>
          <p>
            A série de contratos do portal municipal ainda não está disponível
            nesta consulta. Isso é limitação de coleta ou consulta — não
            significa ausência de contratos.
          </p>
        </div>
      </section>
    );
  }
  return (
    <section className="finance-documents" aria-labelledby="municipal-contracts-title">
      <div className="section-heading compact">
        <span className="eyebrow">Portal municipal</span>
        <h2 id="municipal-contracts-title">Contratos da Prefeitura</h2>
        <p>
          Série complementar ao PNCP, espelhada do portal de transparência
          municipal: contratado, valor publicado como texto oficial e o PDF do
          contrato. Valores não são convertidos nem somados. CPF de pessoa
          física nunca é exibido.
        </p>
      </div>
      <details className="finance-details">
        <summary>
          Ver os {result.contracts.length.toLocaleString("pt-BR")} contratos mais recentes
        </summary>
        <div className="digest-grid">
          {result.contracts.map((contract) => (
            <MunicipalContractCard contract={contract} key={contract.contractId} />
          ))}
        </div>
      </details>
    </section>
  );
}

export default async function ProcurementsPage({ searchParams }: ProcurementsPageProps) {
  const params = await searchParams;
  const filters: ProcurementFilters = {
    supplierKey: cleanFilter(params.fornecedor, 200),
    fiscalYear: parseYear(params.ano),
    query: cleanFilter(params.q, 120),
    modality: cleanFilter(params.modalidade, 120),
    status: cleanFilter(params.situacao, 120),
    unit: cleanFilter(params.orgao, 160),
  };
  const hasFilters = Boolean(
    filters.supplierKey ||
      filters.fiscalYear ||
      filters.query ||
      filters.modality ||
      filters.status ||
      filters.unit,
  );
  const [
    result,
    supplierResult,
    filterOptionsResult,
    municipalContractsResult,
    municipalProcessesResult,
    supplierSanctionsResult,
  ] = await Promise.all([
    getPncpProcurements(filters),
    hasFilters
      ? Promise.resolve({ state: "available" as const, suppliers: [] as const })
      : getPublicSupplierConcentration(),
    getPncpProcurementFilterOptions(),
    getPublicMunicipalContracts(),
    getPublicMunicipalProcurementProcesses(),
    getPublicSupplierSanctions(),
  ]);
  const filterOptions =
    filterOptionsResult.state === "available" ? filterOptionsResult.options : [];

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
          <label>
            Modalidade
            <input list="pncp-modalidades" name="modalidade" defaultValue={filters.modality ?? ""} placeholder="Ex.: Dispensa" />
            <datalist id="pncp-modalidades">
              {optionsFor(filterOptions, "modalidade").map((option) => (
                <option key={option.value} value={option.value} label={optionLabel(option)} />
              ))}
            </datalist>
          </label>
          <label>
            Situação
            <input list="pncp-situacoes" name="situacao" defaultValue={filters.status ?? ""} placeholder="Ex.: Suspensa" />
            <datalist id="pncp-situacoes">
              {optionsFor(filterOptions, "situacao").map((option) => (
                <option key={option.value} value={option.value} label={optionLabel(option)} />
              ))}
            </datalist>
          </label>
          <label className="procurement-filter-query">
            Órgão ou unidade
            <input list="pncp-orgaos" name="orgao" defaultValue={filters.unit ?? ""} placeholder="Ex.: MUNICIPIO DE BARREIRAS-BA" />
            <datalist id="pncp-orgaos">
              {optionsFor(filterOptions, "orgao").map((option) => (
                <option key={option.value} value={option.value} label={optionLabel(option)} />
              ))}
            </datalist>
          </label>
          <div className="procurement-filter-actions">
            <button type="submit">Filtrar</button>
            {hasFilters ? <a className="button-secondary" href="/licitacoes">Limpar</a> : null}
          </div>
        </form>
        <p className="procurement-filter-note">
          Use este único painel para pesquisar. Os resultados abaixo já vêm filtrados pela consulta
          oficial preservada do PNCP.
        </p>

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

        <SupplierSanctionsPanel result={supplierSanctionsResult} />

        <MunicipalContractsPanel result={municipalContractsResult} />
        <MunicipalProcessesPanel result={municipalProcessesResult} />

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
