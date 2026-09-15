import {getPharmacyExport} from '../../../../lib/pharmacy';
import {serializePharmacyCsv} from '../../../../lib/pharmacy-csv.mjs';
import {validPharmacySelection} from '../../../../lib/pharmacy-establishments.mjs';

export const dynamic='force-dynamic';
export const revalidate=0;
const headers={'Cache-Control':'no-store, max-age=0','X-Content-Type-Options':'nosniff'};
const errorResponse=(message:string,status:number)=>new Response(message+'\n',{
  status,headers:{...headers,'Content-Type':'text/plain; charset=utf-8'},
});

export async function GET(request:Request):Promise<Response>{
  const params=new URL(request.url).searchParams;
  const yearText=params.get('ano'),selection=params.get('estabelecimento');
  if([...params.keys()].some(key=>!['ano','estabelecimento'].includes(key))||params.getAll('ano').length!==1||
    params.getAll('estabelecimento').length>1||!yearText||!/^\d{4}$/.test(yearText)||
    Number(yearText)<2021||Number(yearText)>2100||!validPharmacySelection(selection)){
    return errorResponse('Consulta inválida. Volte à página de saúde e escolha o ano e o estabelecimento.',400);
  }
  try{
    const result=await getPharmacyExport(Number(yearText),selection);
    if(result.status==='pending')return errorResponse('Ainda não há pagamentos publicados nesta seleção. Isso não significa que a fonte informou zero.',409);
    if(result.status!=='ready')throw Error('Unavailable');
    const csv=serializePharmacyCsv(result);
    return new Response(csv,{headers:{...headers,'Content-Type':'text/csv; charset=utf-8',
      'Content-Disposition':`attachment; filename="farmacia-popular-${yearText}${selection===null?'':'-estabelecimento'}.csv"`}});
  }catch{
    return errorResponse('Não foi possível validar o arquivo completo. Escolha um estabelecimento para reduzir a consulta ou tente novamente. Isso não significa que os pagamentos foram zero.',503);
  }
}
