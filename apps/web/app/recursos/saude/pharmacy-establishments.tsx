import { pharmacyHref, validPharmacySelection } from '../../../lib/pharmacy-establishments.mjs';
import type { PharmacyEstablishments as Options } from '../../../lib/pharmacy-establishments.mjs';

export function PharmacyEstablishments({year,page,optionsPage,selection,selectedName,options}:{
  year:number;page:number;optionsPage:number;selection:string|null;selectedName?:string;options:Options;
}) {
  const validSelection=validPharmacySelection(selection);
  const validPages=Number.isInteger(page)&&page>=1&&page<=401&&Number.isInteger(optionsPage)&&optionsPage>=1&&optionsPage<=401;
  return <aside className="transfer-reading-guide pharmacy-establishment-filter" aria-labelledby="pharmacy-filter-title">
    <h2 id="pharmacy-filter-title">Filtrar por estabelecimento</h2>
    <p>{selection===null ? 'Exibindo todos os estabelecimentos publicados neste ano.' : selectedName ?
      <>Selecionado: <strong>{selectedName}</strong></> : 'Não foi possível validar o estabelecimento selecionado. Nenhum filtro é removido automaticamente.'}</p>
    {selection!==null && <p><a href={pharmacyHref(year)}>Ver todos os estabelecimentos</a></p>}
    <details><summary>Escolher estabelecimento</summary>
      <p>Opções com pagamentos publicados em {year}. Não é o cadastro completo de farmácias.
        Nomes iguais podem pertencer a estabelecimentos diferentes.</p>
      {options.status==='unavailable' ? <p>As opções de estabelecimento estão temporariamente indisponíveis.</p> : <>
        {options.records.length===0 ? <p>Nenhuma opção nesta página. Isso não comprova ausência de pagamentos na fonte oficial.</p> :
          <ul>{options.records.map(option=><li key={option.establishment_id}>
            <a href={pharmacyHref(year,{establishment:option.establishment_id})}>{option.establishment}</a>
            <details><summary>Referência documental</summary><p><code>{option.establishment_id}</code></p></details>
          </li>)}</ul>}
        {validSelection&&validPages&&<nav aria-label="Páginas dos estabelecimentos">
          <p>Opções · Página {optionsPage} · Até 25 por página</p>
          {optionsPage>1&&<p><a href={pharmacyHref(year,{establishment:selection,page,optionsPage:optionsPage-1})}>← Opções anteriores</a></p>}
          {options.hasNext&&<p><a href={pharmacyHref(year,{establishment:selection,page,optionsPage:optionsPage+1})}>Mais estabelecimentos →</a></p>}
        </nav>}
      </>}
    </details>
  </aside>;
}
