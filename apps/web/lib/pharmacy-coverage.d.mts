export type PharmacyCoverage = {status:'unavailable'} | {status:'partial'|'pending';year:number;published_documents:number;establishments:number;first_date:string|null;last_date:string|null};
export function loadPharmacyCoverage(year:number,callRpc:(args:{p_year:number})=>Promise<unknown>):Promise<PharmacyCoverage>;
