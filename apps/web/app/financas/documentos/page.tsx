import type { Metadata } from "next";
import { connection } from "next/server";
import styles from "./catalog.module.css";
import { FINANCE_DOCUMENT_RESOURCES, FINANCE_DOCUMENT_PAGE_SIZE,
  financeResourceLabel, getPublicFinanceDocumentPage } from "../../../lib/finance-documents";

export const metadata: Metadata = {title:"Documentos financeiros por ano",description:"Consulte referências financeiras preservadas de Barreiras por ano e tipo de documento, com fonte oficial."};

export default async function FinanceDocumentPage({searchParams}: {
  searchParams: Promise<Record<string,string|string[]|undefined>>;
}) {
  await connection();
  const params = await searchParams;
  const year = typeof params.ano === "string" && params.ano ? Number(params.ano) : null;
  const resource = typeof params.tipo === "string" && params.tipo ? params.tipo : null;
  const page = typeof params.pagina === "string" ? Number(params.pagina) : 1;
  const result = await getPublicFinanceDocumentPage(year,resource,page);
  const href = (target:number) => {
    const query = new URLSearchParams({pagina:String(target)});
    if (year !== null) query.set("ano",String(year));
    if (resource) query.set("tipo",resource);
    return `/financas/documentos?${query}#resultados`;
  };
  return <main>
    <nav className="page-back" aria-label="Voltar"><a href="/financas#document-title">← Finanças</a></nav>
    <section className="section" aria-labelledby="documents-title">
      <div className="section-heading">
        <span className="eyebrow">Fontes oficiais</span>
        <h1 id="documents-title">Documentos financeiros por ano</h1>
        <p>Explore as referências preservadas do catálogo da Prefeitura. O total desta consulta não comprova que todo o portal oficial foi coletado nem representa a quantidade de PDFs distintos.</p>
      </div>
      <form className={styles.filters} action="/financas/documentos" method="get" aria-label="Filtros de documentos">
        <label>Ano informado pela fonte<input name="ano" type="number" min="1900" max="2100" placeholder="Todos os anos" defaultValue={year !== null && Number.isInteger(year) ? year : ""} /></label>
        <label>Tipo de documento<select name="tipo" defaultValue={resource ?? ""}>
          <option value="">Todos os tipos</option>
          {FINANCE_DOCUMENT_RESOURCES.map(value=><option value={value} key={value}>{financeResourceLabel(value)}</option>)}
        </select></label>
        <button type="submit">Consultar documentos</button>
        <a href="/financas/documentos">Limpar filtros</a>
      </form>
      {result.state === "unavailable" ? <p role="status">Não foi possível consultar os documentos. Confira os filtros ou tente novamente. Isso não significa ausência de documentos na fonte oficial.</p> : <>
        <p>Anos encontrados neste tipo de catálogo: {result.availableYears.join(", ") || "nenhum ano informado"}. Documentos sem ano aparecem em “Todos os anos”.</p>
        <div id="resultados" tabIndex={-1}>
          <h2>{result.totalCount.toLocaleString("pt-BR")} referências no recorte consultado</h2>
          <p>{result.documents.length} nesta página · página {page} de {Math.max(1,Math.ceil(result.totalCount/FINANCE_DOCUMENT_PAGE_SIZE))}. Até {FINANCE_DOCUMENT_PAGE_SIZE} por página, sem carregar os arquivos integrais no navegador.</p>
          {result.documents.length===0 ? <p>Nenhuma referência nesta página. Isso não comprova ausência na fonte. <a href={href(1)}>Voltar à primeira página</a>.</p> : null}
          <div className={`digest-grid ${styles.catalog}`}>
            {result.documents.map(document=><article className="digest-card" key={document.documentId}>
              <div className="track-top"><span>{financeResourceLabel(document.sourceResource)}</span><span>{document.fiscalYear ?? "Ano não informado"}</span></div>
              <h3 className="procurement-object">{document.title}</h3>
              <p>Referência: {document.referenceDate ?? "não informada"}</p>
              <p>{document.documentPreserved ? "Arquivo preservado" : "Referência preservada; arquivo ainda não preservado"}.</p>
              <p className="act-evidence"><a href={document.documentUrl} target="_blank" rel="noreferrer">Abrir documento oficial ↗</a> · <a href={document.apiSourceUrl} target="_blank" rel="noreferrer">Catálogo de origem ↗</a> · hash da resposta {document.artifactSha256.slice(0,12)}…</p>
            </article>)}
          </div>
          <nav className="finance-coverage-jump-nav" aria-label="Páginas de documentos">
            {page>1 ? <a href={href(page-1)} rel="prev">← Página anterior</a> : null}
            {page*FINANCE_DOCUMENT_PAGE_SIZE<result.totalCount ? <a href={href(page+1)} rel="next">Próxima página →</a> : null}
          </nav>
        </div>
      </>}
      <p><a href="/financas/cobertura">Consultar os calendários e seus limites de cobertura →</a></p>
    </section>
  </main>;
}
