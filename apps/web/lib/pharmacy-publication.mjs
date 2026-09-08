// Only consume a server-side, reviewed public projection, never raw FNS JSON.
// These checks supplement, not replace, database publication authorization.
export function readPharmacyPublication(input) {
  if (input == null) return { status: 'pending', records: [] };
  const blocked = { status: 'unavailable', records: [] };
  if (input.approved !== true || input.evidenceCurrent !== true ||
      !Number.isInteger(input.year) || input.year < 2021 || input.year > 2100 ||
      !Array.isArray(input.records) || input.records.length === 0 || input.records.length > 25) return blocked;
  const seen = new Set();
  const records = [];
  for (const row of input.records) {
    if (!row || typeof row.id !== 'string' || !/^[a-zA-Z0-9-]{1,80}$/.test(row.id) || seen.has(row.id) ||
        row.identityVerified !== true || row.reconciliation !== 'standalone_fns' ||
        row.program !== 'FARMACIA POPULAR' || row.municipality !== '290320' || row.beneficiaryType !== 'institution' ||
        typeof row.establishment !== 'string' || row.establishment.trim().length < 2 || row.establishment.length > 180 ||
        typeof row.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256) ||
        typeof row.amount !== 'string' || !/^\d{1,12}\.\d{2}$/.test(row.amount) ||
        typeof row.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) return blocked;
    const date = new Date(`${row.date}T00:00:00Z`);
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0,10) !== row.date || date.getUTCFullYear() !== input.year) return blocked;
    seen.add(row.id);
    records.push({id:row.id, establishment:row.establishment.trim(), date:row.date, amount:row.amount, sha256:row.sha256});
  }
  return { status: 'ready', year: input.year, records };
}
