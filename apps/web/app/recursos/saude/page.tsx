import type { Metadata } from 'next';
import { getPharmacyPage } from '../../../lib/pharmacy';
import { PharmacyPayments } from './pharmacy-payments';

export const metadata: Metadata = { title: 'Recursos da saúde' };

export default async function HealthResourcesPage({searchParams}:{searchParams:Promise<{ano?:string;pagina?:string}>}) {
  const params=await searchParams;
  const year=params.ano===undefined ? 2025 : Number(params.ano);
  const page=params.pagina===undefined ? 1 : Number(params.pagina);
  const {publication,hasNext}=await getPharmacyPage(year,page);
  const validScope=Number.isInteger(year)&&year>=2021&&year<=2100&&Number.isInteger(page)&&page>=1&&page<=401;
  const years=Array.from(new Set([...Array.from({length:new Date().getUTCFullYear()-2020},(_,i)=>2021+i),validScope?year:2025])).sort((a,b)=>b-a);
  return <main><header className="site-header"><a href="/recursos">← Recursos de Barreiras</a></header>
    <PharmacyPayments publication={publication} filters={
      <form className="transfer-year-filter" action="/recursos/saude" method="get" aria-label="Filtrar pagamentos por ano">
        <div><label htmlFor="pharmacy-year">Ano do pagamento</label>
          <select id="pharmacy-year" name="ano" defaultValue={validScope?year:2025}>
            {years.map(y=><option key={y} value={y}>{y}</option>)}
          </select></div>
        <button type="submit">Consultar</button>
      </form>
    } navigation={validScope && <nav aria-label="Páginas dos pagamentos">
      <p>Ano {year} · Página {page} · Até 25 registros por página</p>
      {page>1 && <a href={`?ano=${year}&pagina=${page-1}`}>← Página anterior</a>}
      {hasNext && <p><a href={`?ano=${year}&pagina=${page+1}`}>Próxima página →</a></p>}
    </nav>}/>
  </main>;
}
