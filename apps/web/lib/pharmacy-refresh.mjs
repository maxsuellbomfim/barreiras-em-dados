export async function loadPharmacyRefresh(year, callRpc) {
  const unavailable = {status:'unavailable'};
  if (!Number.isInteger(year) || year<2021 || year>2100) return unavailable;
  try {
    const rows=await callRpc({p_year:year});
    if (!Array.isArray(rows) || rows.length!==1) return unavailable;
    const r=rows[0];
    if (!r || r.year!==year || !['not_started','running','failed','partial','complete','empty'].includes(r.status)) return unavailable;
    const dates=['last_attempt_at','completed_at','last_verified_at'];
    const counts=['verified_documents','pending_scopes','missing_scopes'];
    const validTime=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
    if (dates.some(key=>r[key]!==null && !validTime(r[key]))) return unavailable;
    if (r.status==='not_started') {
      if ([...dates,...counts].some(key=>r[key]!==null)) return unavailable;
    } else {
      if (!validTime(r.last_attempt_at)) return unavailable;
      if (r.completed_at!==null && Date.parse(r.completed_at)<Date.parse(r.last_attempt_at)) return unavailable;
      if (r.last_verified_at!==null && Date.parse(r.last_verified_at)>Date.parse(r.completed_at??r.last_attempt_at)) return unavailable;
      if (['running','failed'].includes(r.status)) {
        if (counts.some(key=>r[key]!==null) || (r.status==='running' && r.completed_at!==null)) return unavailable;
      } else {
        if (!validTime(r.completed_at) || counts.some(key=>!Number.isSafeInteger(r[key])||r[key]<0||r[key]>9999999)) return unavailable;
        if (r.status!=='partial' && (r.pending_scopes!==0||r.missing_scopes!==0)) return unavailable;
        if (r.status==='empty' && r.verified_documents!==0) return unavailable;
      }
    }
    return {year,status:r.status,...Object.fromEntries([...dates,...counts].map(key=>[key,r[key]]))};
  } catch {return unavailable;}
}
