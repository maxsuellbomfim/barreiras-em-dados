export type PharmacyEstablishment={establishment_id:string;establishment:string};
export type PharmacyEstablishments={status:'ready'|'unavailable';records:PharmacyEstablishment[];hasNext:boolean};
export function validPharmacySelection(value:unknown):boolean;
export function validPharmacyName(value:unknown):boolean;
export function pharmacyHref(year:number,options?:{page?:number;establishment?:string|null;optionsPage?:number}):string;
export function loadPharmacyEstablishments(year:number,page:number,callRpc:(args:{p_year:number;p_offset:number})=>Promise<unknown>):Promise<PharmacyEstablishments>;
