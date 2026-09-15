import type {PharmacyCoverage} from '../../../lib/pharmacy-coverage.mjs';
import {pharmacyExportHref,PHARMACY_EXPORT_LIMIT} from '../../../lib/pharmacy-csv.mjs';
import {validPharmacySelection} from '../../../lib/pharmacy-establishments.mjs';

export function PharmacyExportLink({year,selection,coverage}:{year:number;selection:string|null;coverage:PharmacyCoverage}){
  if(!Number.isInteger(year)||year<2021||year>2100||!validPharmacySelection(selection)||
    coverage.status!=='partial'||coverage.year!==year||!coverage.published_documents||
    Boolean(coverage.filter_applied)!==(selection!==null))return null;
  return <aside className="transfer-reading-guide pharmacy-export" aria-labelledby="pharmacy-export-title">
    <h2 id="pharmacy-export-title">Leve os dados para sua análise</h2>
    {coverage.published_documents>PHARMACY_EXPORT_LIMIT?<p>A seleção ultrapassa 5.000 pagamentos. Escolha um estabelecimento para reduzir o arquivo.</p>:<>
      <p><a href={pharmacyExportHref(year,selection)} download>Baixar consulta em CSV</a></p>
      <p>Inclui todas as páginas do ano{selection!==null?' e do estabelecimento selecionado':''}, com fontes e aviso de cobertura parcial.
        Os registros são conferidos novamente no download e podem refletir uma atualização posterior à tela.</p>
      <details><summary>Como abrir na planilha</summary>
        <p>Use UTF-8, ponto e vírgula como separador e vírgula decimal. Valores estão em reais, sem soma entre programas.</p>
        <p>Um apóstrofo inicial protege textos que a planilha poderia tratar como fórmula ou número.
          Essa proteção não muda os valores dos pagamentos. Limite de 5.000 registros e 4 MB por arquivo.</p>
      </details>
    </>}
  </aside>;
}
