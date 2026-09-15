import type { PharmacyPublication } from './pharmacy-publication.mjs';
export function readPharmacyRows(rows:unknown,year:number):PharmacyPublication;
export function loadPharmacyPage(year:number,page:number,callRpc:(args:{p_year:number;p_offset:number;p_establishment_id?:string})=>Promise<unknown>,establishment?:string|null):Promise<{publication:PharmacyPublication;hasNext:boolean}>;
