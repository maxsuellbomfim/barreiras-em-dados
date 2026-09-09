import { fetchPublicRpcRows } from './public-rpc.mjs';
import { loadPharmacyPage } from './pharmacy-loader.mjs';
import { loadPharmacyCoverage } from './pharmacy-coverage.mjs';
import { loadPharmacyRefresh } from './pharmacy-refresh.mjs';

export async function getPharmacyPage(year:number,page:number) {
  return loadPharmacyPage(year,page,args=>callPharmacyRpc('get_public_pharmacy_payments',args));
}

export async function getPharmacyCoverage(year:number) {
  return loadPharmacyCoverage(year,args=>callPharmacyRpc('get_public_pharmacy_coverage',args));
}

export async function getPharmacyRefresh(year:number) {
  return loadPharmacyRefresh(year,args=>callPharmacyRpc('get_public_pharmacy_refresh',args));
}

async function callPharmacyRpc(name:'get_public_pharmacy_payments'|'get_public_pharmacy_coverage'|'get_public_pharmacy_refresh',args:object) {
  const url=process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key=process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
    if(!url || !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url) || !key?.startsWith('sb_publishable_')) throw Error('Unavailable');
    return fetchPublicRpcRows({url:`${url}/rest/v1/rpc/${name}`,
      headers:{Accept:'application/json','Accept-Profile':'api','Content-Profile':'api',
        'Content-Type':'application/json',apikey:key},body:JSON.stringify(args)},
      {revalidateSeconds:0,timeoutMs:5000});
}
