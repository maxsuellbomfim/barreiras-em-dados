export type PharmacyRefresh = {status:'unavailable'} | {
  status:'not_started'|'running'|'failed'|'partial'|'complete'|'empty';year:number;
  last_attempt_at:string|null;completed_at:string|null;last_verified_at:string|null;
  verified_documents:number|null;pending_scopes:number|null;missing_scopes:number|null;
};
export function loadPharmacyRefresh(year:number,callRpc:(args:{p_year:number})=>Promise<unknown>):Promise<PharmacyRefresh>;
