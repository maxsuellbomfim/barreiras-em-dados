import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const cnpj = '13654405000195';
const contractPattern = /^13654405000195-2-[0-9]{1,12}\/[0-9]{4}$/;
const parentPattern = /^[0-9]{14}-1-[0-9]{1,12}\/[0-9]{4}$/;
function requireValue(ok) { if (!ok) throw new Error('Invalid or incomplete inventory evidence'); }
function date(value) {
  requireValue(typeof value === 'string' && /^\d{8}$/.test(value));
  const iso = `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}`;
  const parsed = new Date(`${iso}T00:00:00Z`);
  requireValue(Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0,10) === iso);
  return parsed.getTime();
}

// Read-only comparison, not an import/publication gate. A single fully returned
// publication window is deliberately required; split larger periods explicitly.
export function auditContractInventory(payload, inventory, { since, until }) {
  requireValue(date(since) <= date(until));
  requireValue(date(until) - date(since) <= 366 * 86400000);
  requireValue(payload && Array.isArray(payload.data) && payload.data.length <= 500);
  requireValue(Number.isInteger(payload.totalRegistros) && payload.totalRegistros === payload.data.length);
  requireValue(payload.numeroPagina === 1 && payload.paginasRestantes === 0);
  requireValue(payload.empty === (payload.data.length === 0));
  requireValue(payload.totalPaginas === 1 || (payload.data.length === 0 && payload.totalPaginas === 0));
  requireValue(Array.isArray(inventory) && inventory.length <= 100000);
  const known = new Map();
  for (const row of inventory) {
    requireValue(row && contractPattern.test(row.contract_control) &&
      (row.procurement_control === null || parentPattern.test(row.procurement_control)) && !known.has(row.contract_control));
    known.set(row.contract_control, row.procurement_control);
  }
  const seen = new Set();
  const missing = [], cross = [], conflicts = [];
  for (const row of payload.data) {
    requireValue(row && typeof row === 'object');
    const contract = row.numeroControlePNCP;
    const parent = row.numeroControlePncpCompra;
    requireValue(contractPattern.test(contract) && parentPattern.test(parent) && row.orgaoEntidade?.cnpj === cnpj);
    requireValue(typeof row.dataPublicacaoPncp === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(row.dataPublicacaoPncp));
    const published = row.dataPublicacaoPncp.slice(0,10).replaceAll('-','');
    requireValue(date(published) >= date(since) && date(published) <= date(until) && !seen.has(contract));
    seen.add(contract);
    if (!known.has(contract)) missing.push(contract);
    if (!parent.startsWith(`${cnpj}-1-`)) cross.push({ contract, procurement: parent });
    if (known.has(contract) && known.get(contract) !== parent)
      conflicts.push({ contract, source_procurement: parent, inventory_procurement: known.get(contract) });
  }
  return {
    gate: missing.length || cross.length || conflicts.length ? 'REVIEW' : 'MATCH',
    scope: 'publication_window_inventory', since, until,
    source_contracts: seen.size, matched_contracts: seen.size - missing.length,
    missing_contracts: missing.sort(), cross_organization_links: cross,
    link_conflicts: conflicts, publication_authorized: false,
  };
}

async function main() {
  const [since, until, inventoryPath, ...extra] = process.argv.slice(2);
  requireValue(extra.length === 0 && inventoryPath && date(since) <= date(until));
  requireValue(date(until) - date(since) <= 366 * 86400000);
  const inventory = JSON.parse(readFileSync(inventoryPath, 'utf8'));
  const url = new URL('https://pncp.gov.br/api/consulta/v1/contratos');
  url.search = new URLSearchParams({dataInicial:since,dataFinal:until,cnpjOrgao:cnpj,pagina:'1',tamanhoPagina:'500'}).toString();
  const response = await fetch(url, {signal:AbortSignal.timeout(60000), headers:{Accept:'application/json'}});
  requireValue(response.status === 200);
  const text = await response.text();
  requireValue(Buffer.byteLength(text) <= 8 * 1024 * 1024);
  const result = auditContractInventory(JSON.parse(text), inventory, {since,until});
  console.log(JSON.stringify({...result,source_url:url.toString(),checked_at:new Date().toISOString()}));
  if (result.gate !== 'MATCH') process.exitCode = 2;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(() => { console.error('Inventory audit failed; no coverage or publication conclusion.'); process.exitCode=1; });
