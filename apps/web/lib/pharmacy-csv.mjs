import {readPharmacyRows} from './pharmacy-loader.mjs';
import {pharmacyHref,validPharmacyName,validPharmacySelection} from './pharmacy-establishments.mjs';

export const PHARMACY_EXPORT_LIMIT=5000;
const validYear=year=>Number.isInteger(year)&&year>=2021&&year<=2100;

export function pharmacyExportHref(year,establishment=null){
  return '/recursos/saude/exportar'+pharmacyHref(year,{establishment});
}

// One public RPC envelope represents one database statement snapshot. Batching
// below is in-memory validation only, never separate requests for further pages.
export async function loadPharmacyExport(year,callRpc,establishment=null){
  const unavailable={status:'unavailable'};
  if(!validYear(year)||!validPharmacySelection(establishment))return unavailable;
  try{
    const payload=await callRpc({p_year:year,...(establishment===null?{}:{p_establishment_id:establishment})});
    if(!Array.isArray(payload)||payload.length!==1)return unavailable;
    const scope=payload[0];
    if(!scope||scope.year!==year||scope.filter_applied!==(establishment!==null)||
      !Array.isArray(scope.records)||scope.records.length>PHARMACY_EXPORT_LIMIT||
      scope.published_documents!==scope.records.length||!Number.isInteger(scope.establishments)||
      scope.establishments<0||scope.establishments>scope.records.length)return unavailable;
    if(establishment===null?scope.selected_establishment!==null:
      (!validPharmacyName(scope.selected_establishment)||scope.establishments!==1))return unavailable;
    if(scope.records.length===0){
      return scope.status==='pending'&&establishment===null&&scope.establishments===0?{status:'pending'}:unavailable;
    }
    if(scope.status!=='partial'||scope.establishments<1)return unavailable;
    const records=[],seen=new Set();
    for(let offset=0;offset<scope.records.length;offset+=25){
      const batch=readPharmacyRows(scope.records.slice(offset,offset+25),year);
      if(batch.status!=='ready')return unavailable;
      for(const row of batch.records){
        if(!/^[a-f0-9]{64}$/.test(row.id)||seen.has(row.id)||
          (establishment!==null&&row.establishment!==scope.selected_establishment.trim()))return unavailable;
        const previous=records.at(-1);
        if(previous&&(previous.date<row.date||(previous.date===row.date&&previous.id>row.id)))return unavailable;
        seen.add(row.id);records.push(row);
      }
    }
    if(establishment!==null&&!seen.has(establishment))return unavailable;
    return {status:'ready',year,establishment,records};
  }catch{return unavailable;}
}

function textCell(value){
  // Quotes delimit CSV but do not stop a spreadsheet executing a formula.
  // Also protect numeric/scientific text identifiers against rounding/coercion.
  const protectedValue=/^[\s\uFEFF]*[=+\-@\uFF1D\uFF0B\uFF0D\uFF20]/u.test(value)||
    /^\s*\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?\s*$/.test(value)?`'${value}`:value;
  return quote(protectedValue);
}
const quote=value=>`"${value.replaceAll('"','""')}"`;

export function serializePharmacyCsv(result,exportedAt=new Date().toISOString()){
  if(result.status!=='ready'||!validYear(result.year)||!validPharmacySelection(result.establishment)||
    result.records.length===0||result.records.length>PHARMACY_EXPORT_LIMIT||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(exportedAt)||
    !Number.isFinite(Date.parse(exportedAt)))throw Error('Invalid pharmacy export');
  const header=['ano','referencia_filtro','documento','estabelecimento','data_documento','valor_liquido_brl','sha256',
    'fonte_consulta_geral','escopo','extraido_em_utc'];
  const lines=[header.map(quote).join(';')];
  for(const row of result.records){
    if(!/^\d{1,12}\.\d{2}$/.test(row.amount))throw Error('Invalid pharmacy amount');
    lines.push([quote(String(result.year)),textCell(result.establishment??''),textCell(row.id),textCell(row.establishment),
      quote(row.date),quote(row.amount.replace('.',',')),textCell(row.sha256),
      quote('https://consultafns.saude.gov.br/#/detalhada'),
      quote('Cobertura parcial: pagamentos publicados desta seleção; não é receita da Prefeitura nem comprovação da execução do serviço.'),
      quote(exportedAt)].join(';'));
  }
  const csv='\uFEFF'+lines.join('\r\n')+'\r\n';
  if(new TextEncoder().encode(csv).byteLength>4_000_000)throw Error('Pharmacy export size exceeded');
  return csv;
}
