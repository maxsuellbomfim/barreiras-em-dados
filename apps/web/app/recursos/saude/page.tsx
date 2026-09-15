import type { Metadata } from 'next';
import { getPharmacyPage, getPharmacyCoverage, getPharmacyRefresh, getPharmacyEstablishments } from '../../../lib/pharmacy';
import { pharmacyHref, validPharmacySelection } from '../../../lib/pharmacy-establishments.mjs';
import { PharmacyPayments } from './pharmacy-payments';
import { PharmacyRefreshStatus } from './pharmacy-refresh';
import { PharmacyEstablishments } from './pharmacy-establishments';
import { PharmacyExportLink } from './pharmacy-export';

export const metadata: Metadata = { title: 'Recursos da saúde' };

export default async function HealthResourcesPage({searchParams}:{searchParams:Promise<{ano?:string|string[];pagina?:string|string[];estabelecimento?:string|string[];opcoes?:string|string[]}>}) {
  const params=await searchParams;
  const year=params.ano===undefined ? 2025 : typeof params.ano==='string'?Number(params.ano):NaN;
  const page=params.pagina===undefined ? 1 : typeof params.pagina==='string'?Number(params.pagina):NaN;
  const optionsPage=params.opcoes===undefined ? 1 : typeof params.opcoes==='string'?Number(params.opcoes):NaN;
  const selection=params.estabelecimento===undefined?null:typeof params.estabelecimento==='string'?params.estabelecimento:'';
  const [{publication,hasNext},coverage,refresh,options]=await Promise.all([
    getPharmacyPage(year,page,selection),getPharmacyCoverage(year,selection),getPharmacyRefresh(year),getPharmacyEstablishments(year,optionsPage)]);
  const validYear=Number.isInteger(year)&&year>=2021&&year<=2100;
  const validScope=validYear&&Number.isInteger(page)&&page>=1&&page<=401&&validPharmacySelection(selection);
  const years=Array.from(new Set([...Array.from({length:new Date().getUTCFullYear()-2020},(_,i)=>2021+i),validYear?year:2025])).sort((a,b)=>b-a);
  return <main><header className="site-header"><a href="/recursos">← Recursos de Barreiras</a></header>
    <PharmacyPayments publication={publication} coverage={coverage} filtered={selection!==null}
      firstPageHref={validScope?pharmacyHref(year,{establishment:selection}):undefined} filters={<>
      <form className="transfer-year-filter" action="/recursos/saude" method="get" aria-label="Filtrar pagamentos por ano">
        <div><label htmlFor="pharmacy-year">Ano do pagamento</label>
          <select id="pharmacy-year" name="ano" defaultValue={validYear?year:2025}>
            {years.map(y=><option key={y} value={y}>{y}</option>)}
          </select></div>
        <button type="submit">Consultar</button>
      </form>
      <p>Consultar outro ano reinicia a seleção de estabelecimento e as páginas.</p>
      {validYear&&<PharmacyEstablishments year={year} page={page} optionsPage={optionsPage} selection={selection}
        selectedName={coverage.status==='partial'?coverage.selected_establishment:undefined} options={options}/>}
      <PharmacyExportLink year={year} selection={selection} coverage={coverage}/>
      {selection!==null&&<p>A atualização abaixo se refere ao ano inteiro, antes do filtro por estabelecimento.</p>}
      <PharmacyRefreshStatus refresh={refresh}/>
    </>} navigation={validScope && <nav aria-label="Páginas dos pagamentos">
      <p>Ano {year} · Página {page} · Até 25 registros por página</p>
      {page>1 && <a href={pharmacyHref(year,{page:page-1,establishment:selection})}>← Página anterior</a>}
      {hasNext && <p><a href={pharmacyHref(year,{page:page+1,establishment:selection})}>Próxima página →</a></p>}
    </nav>}/>
  </main>;
}
