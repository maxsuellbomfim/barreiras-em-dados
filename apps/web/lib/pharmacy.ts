import { fetchPublicRpcRows } from './public-rpc.mjs';
import { loadPharmacyPage } from './pharmacy-loader.mjs';

export async function getPharmacyPage(year:number,page:number) {
  const url=process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key=process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return loadPharmacyPage(year,page,async args=>{
    if(!url || !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url) || !key?.startsWith('sb_publishable_')) throw Error('Unavailable');
    return fetchPublicRpcRows({url:`${url}/rest/v1/rpc/get_public_pharmacy_payments`,
      headers:{Accept:'application/json','Accept-Profile':'api','Content-Profile':'api',
        'Content-Type':'application/json',apikey:key},body:JSON.stringify(args)},
      {revalidateSeconds:0,timeoutMs:5000});
  });
}
