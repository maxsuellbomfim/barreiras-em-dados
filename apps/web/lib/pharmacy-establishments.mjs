export const validPharmacySelection=value=>value===null || (typeof value==='string' && /^[a-f0-9]{64}$/.test(value));
export const validPharmacyName=value=>typeof value==='string' && value.trim().length>=2 && value.length<=180 && !/[<>\x00-\x1f\x7f]|[0-9]{11}/.test(value);
const validYear=year=>Number.isInteger(year)&&year>=2021&&year<=2100;
const validPage=page=>Number.isInteger(page)&&page>=1&&page<=401;

export function pharmacyHref(year,{page=1,establishment=null,optionsPage=1}={}) {
  if(!validYear(year)||!validPage(page)||!validPage(optionsPage)||!validPharmacySelection(establishment)) throw Error('Invalid pharmacy navigation');
  const params=new URLSearchParams({ano:String(year)});
  if(establishment!==null) params.set('estabelecimento',establishment);
  if(page>1) params.set('pagina',String(page));
  if(optionsPage>1) params.set('opcoes',String(optionsPage));
  return `?${params}`;
}

function readOptions(rows) {
  if(!Array.isArray(rows)||rows.length>25) throw Error('Invalid options');
  const seen=new Set();
  return rows.map(row=>{
    if(!row || row.establishment_id===null || !validPharmacySelection(row.establishment_id) || !validPharmacyName(row.establishment) || seen.has(row.establishment_id)) throw Error('Invalid option');
    seen.add(row.establishment_id);
    return {establishment_id:row.establishment_id,establishment:row.establishment.trim()};
  });
}

export async function loadPharmacyEstablishments(year,page,callRpc) {
  const unavailable={status:'unavailable',records:[],hasNext:false};
  if(!validYear(year)||!validPage(page)) return unavailable;
  try {
    const records=readOptions(await callRpc({p_year:year,p_offset:(page-1)*25}));
    let hasNext=false;
    if(records.length===25 && page<401) {
      const next=readOptions(await callRpc({p_year:year,p_offset:page*25}));
      if(next.some(r=>records.some(current=>current.establishment_id===r.establishment_id))) return unavailable;
      hasNext=next.length>0;
    }
    return {status:'ready',records,hasNext};
  } catch {return unavailable;}
}
