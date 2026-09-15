import type {PharmacyRecord} from './pharmacy-publication.mjs';
export const PHARMACY_EXPORT_LIMIT:5000;
export type PharmacyExport={status:'ready';year:number;establishment:string|null;records:PharmacyRecord[]}|{status:'pending'|'unavailable'};
export function pharmacyExportHref(year:number,establishment?:string|null):string;
export function loadPharmacyExport(year:number,callRpc:(args:{p_year:number;p_establishment_id?:string})=>Promise<unknown>,establishment?:string|null):Promise<PharmacyExport>;
export function serializePharmacyCsv(result:PharmacyExport,exportedAt?:string):string;
