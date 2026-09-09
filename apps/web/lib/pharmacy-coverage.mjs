export async function loadPharmacyCoverage(year, callRpc) {
  const unavailable={status:'unavailable'};
  if(!Number.isInteger(year)||year<2021||year>2100) return unavailable;
  try {
    const rows=await callRpc({p_year:year});
    if(!Array.isArray(rows)||rows.length!==1) return unavailable;
    const r=rows[0];
    if(!r||r.year!==year||!Number.isSafeInteger(r.published_documents)||r.published_documents<0||
      !Number.isSafeInteger(r.establishments)||r.establishments<0||r.establishments>r.published_documents) return unavailable;
    const validDate=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      value.startsWith(`${year}-`) && Number.isFinite(Date.parse(value)) &&
      new Date(value).toISOString().slice(0,10)===value;
    if(r.published_documents===0 ? r.status!=='pending'||r.establishments!==0||r.first_date!==null||r.last_date!==null :
      r.status!=='partial'||r.establishments<1||!validDate(r.first_date)||!validDate(r.last_date)||r.first_date>r.last_date) return unavailable;
    return {year,published_documents:r.published_documents,establishments:r.establishments,
      first_date:r.first_date,last_date:r.last_date,status:r.status};
  } catch { return unavailable; }
}
