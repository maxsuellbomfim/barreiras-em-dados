import type { PharmacyPublication } from './pharmacy-publication.mjs';
export function loadPharmacyPage(year:number,page:number,callRpc:(args:{p_year:number;p_offset:number})=>Promise<unknown>):Promise<{publication:PharmacyPublication;hasNext:boolean}>;
