import { readPharmacyPublication } from './pharmacy-publication.mjs';
import { validPharmacySelection } from './pharmacy-establishments.mjs';

function parseRows(rows, year) {
  if (!Array.isArray(rows) || rows.length>25) throw Error('Invalid page');
  if (!rows.length) return readPharmacyPublication(null);
  for(const row of rows) {
    if (!row || row.historical_registration_verified!==false ||
      typeof row.register_sha256!=='string' || !/^[a-f0-9]{64}$/.test(row.register_sha256) ||
      typeof row.reviewed_at!=='string' || !Number.isFinite(Date.parse(row.reviewed_at)) ||
      typeof row.establishment!=='string' || /[<>\x00-\x1f\x7f]|[0-9]{11}/.test(row.establishment)) throw Error('Invalid evidence');
  }
  return readPharmacyPublication({approved:true,evidenceCurrent:true,year,
    records:rows.map(row=>({...row,identityVerified:true,reconciliation:'standalone_fns',
      program:'FARMACIA POPULAR',municipality:'290320',beneficiaryType:'institution'}))});
}

// callRpc must be the trusted server-side public RPC, not a user-provided URL.
export async function loadPharmacyPage(year,page,callRpc,establishment=null) {
  const unavailable={publication:{status:'unavailable',records:[]},hasNext:false};
  if(!Number.isInteger(year)||year<2021||year>2100||!Number.isInteger(page)||page<1||page>401||!validPharmacySelection(establishment)) return unavailable;
  const selection=establishment===null?{}:{p_establishment_id:establishment};
  try {
    const rows=await callRpc({p_year:year,p_offset:(page-1)*25,...selection});
    const publication=parseRows(rows,year);
    if(publication.status==='unavailable') return unavailable;
    // Empty offsets say nothing about publication of the entire year.
    if(publication.status==='pending' && page>1) {
      return {publication:{status:'empty_page',year,records:[]},hasNext:false};
    }
    if(publication.status==='pending' && establishment!==null) return unavailable;
    let hasNext=false;
    if(rows.length===25 && page<401) {
      const next=parseRows(await callRpc({p_year:year,p_offset:page*25,...selection}),year);
      if(next.status==='unavailable') return unavailable;
      hasNext=next.status==='ready';
    }
    return {publication,hasNext};
  } catch { return unavailable; }
}
