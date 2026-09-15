import { fetchPublicRpcRows } from './public-rpc.mjs';
import { loadPharmacyPage } from './pharmacy-loader.mjs';
import { loadPharmacyCoverage } from './pharmacy-coverage.mjs';
import { loadPharmacyRefresh } from './pharmacy-refresh.mjs';
import { loadPharmacyEstablishments } from './pharmacy-establishments.mjs';
import { loadPharmacyExport } from './pharmacy-csv.mjs';

export async function getPharmacyExport(year:number,establishment:string|null=null) {
  return loadPharmacyExport(year,args=>callPharmacyRpc('get_public_pharmacy_export',args),establishment);
}

export async function getPharmacyPage(year:number,page:number,establishment:string|null=null) {
  return loadPharmacyPage(year,page,args=>callPharmacyRpc('get_public_pharmacy_payments_filtered',args),establishment);
}

export async function getPharmacyCoverage(year:number,establishment:string|null=null) {
  return loadPharmacyCoverage(year,args=>callPharmacyRpc('get_public_pharmacy_coverage_filtered',args),establishment);
}

export async function getPharmacyEstablishments(year:number,page:number) {
  return loadPharmacyEstablishments(year,page,args=>callPharmacyRpc('get_public_pharmacy_establishments',args));
}

export async function getPharmacyRefresh(year:number) {
  return loadPharmacyRefresh(year,args=>callPharmacyRpc('get_public_pharmacy_refresh',args));
}

async function callPharmacyRpc(name:'get_public_pharmacy_payments_filtered'|'get_public_pharmacy_coverage_filtered'|'get_public_pharmacy_establishments'|'get_public_pharmacy_refresh'|'get_public_pharmacy_export',args:object) {
  const url=process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key=process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
    if(!url || !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url) || !key?.startsWith('sb_publishable_')) throw Error('Unavailable');
    return fetchPublicRpcRows({url:`${url}/rest/v1/rpc/${name}`,
      headers:{Accept:'application/json','Accept-Profile':'api','Content-Profile':'api',
        'Content-Type':'application/json',apikey:key},body:JSON.stringify(args)},
      {revalidateSeconds:0,timeoutMs:5000});
}
