// Conferência automática por agente da amostra do ADR 0096: lê a lista de
// contratos do portal ao vivo (recurso `contratos`, todas as páginas) e, para
// cada caso, procura o número citado. Não é revisão humana; o resultado é
// gravado com rótulo "conferência automática por agente" e evidência por caso.
//
// Uso: node scripts/check-contract-citations.mjs <amostra.json> <saida.json>
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const CHECK_VERSION = "contract-citation-agent-check/1.0.0";
const API = "https://portaldatransparencia.barreiras.ba.gov.br/api/?resource=contratos";
const LIMIT = 50;
const NUMBER = /([0-9]{1,5})\s*([A-Z]?)\s*(?:-\s*([A-Z]+))?\s*\/\s*([0-9]{4})(?:\s+([A-Z]{2,5}))?/;

const [, , samplePath, outputPath] = process.argv;
if (!samplePath || !outputPath) {
  console.error("uso: node scripts/check-contract-citations.mjs <amostra.json> <saida.json>");
  process.exit(2);
}

function nameKey(value) {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/\b(LTDA|LIMITADA|EIRELL?I|EPP|ME|MEI|CIA|S\/?A|S\/?S|DE|DA|DO|DAS|DOS|E)\b/g, " ")
    .replace(/[^A-Z0-9]/g, "");
}

// "183/2023 FMS", "083-FMS/2024" e "1º TERMO ADITIVO ... Nº 283/2021" viram
// { seq, letter, suffix, year, amendment }.
function parseNumber(text) {
  const upper = (text ?? "").toUpperCase();
  const match = NUMBER.exec(upper);
  if (!match) return null;
  return {
    seq: String(Number(match[1])),
    letter: match[2] ?? "",
    suffix: match[3] ?? match[5] ?? "",
    year: match[4],
    amendment: /ADITIVO|APOSTILA|RERRATIFICA|TERMO/.test(upper),
  };
}

async function readPortalList() {
  const contracts = [];
  const pages = [];
  for (let offset = 0; ; offset += LIMIT) {
    const url = `${API}&limit=${LIMIT}&offset=${offset}`;
    const response = await fetch(url, { signal: AbortSignal.timeout(60_000) });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    const body = await response.text();
    const json = JSON.parse(body);
    if (json.error) throw new Error(`${url}: ${json.error}`);
    pages.push({ url, count: json.count, sha256: createHash("sha256").update(body).digest("hex") });
    contracts.push(...json.data);
    if (json.count < LIMIT || json.data.length === 0) break;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return { contracts, pages };
}

function evaluate(sampleCase, contracts) {
  const cited = parseNumber(sampleCase.cited_number);
  const creditorKey = nameKey(sampleCase.creditor_name);
  const findings = [];
  for (const contract of contracts) {
    const number = parseNumber(contract.contratoNumero);
    if (!number || number.seq !== cited.seq) continue;
    const sameYear = number.year === cited.year;
    const sameSupplier = nameKey(contract.favorecido) === creditorKey;
    const exact = sameYear && number.letter === cited.letter && number.suffix === cited.suffix
      && !number.amendment;
    findings.push({
      portal_id: contract.id,
      contract_number: contract.contratoNumero,
      supplier: contract.favorecido,
      same_year: sameYear,
      same_supplier: sameSupplier,
      exact,
      amendment: number.amendment,
    });
  }
  const supplierOther = contracts
    .filter((contract) => nameKey(contract.favorecido) === creditorKey)
    .map((contract) => contract.contratoNumero);
  let outcome = "ausente_da_lista";
  if (findings.some((finding) => finding.exact)) outcome = "presente_exato";
  else if (findings.some((finding) => finding.same_year && finding.same_supplier && finding.amendment)) {
    outcome = "presente_como_aditivo";
  } else if (findings.some((finding) => finding.same_year && finding.same_supplier)) {
    outcome = "presente_com_outro_sufixo";
  }
  return { ...sampleCase, outcome, same_number_rows: findings, supplier_other_contracts: supplierOther };
}

const sample = JSON.parse(await readFile(samplePath, "utf8"));
const readAt = new Date().toISOString();
const { contracts, pages } = await readPortalList();
const cases = sample.map((sampleCase) => evaluate(sampleCase, contracts));
const counts = {};
for (const item of cases) counts[item.outcome] = (counts[item.outcome] ?? 0) + 1;
// A regra só está certa se nenhum caso estiver na lista com o mesmo número e o
// mesmo fornecedor; aditivo ou sufixo diferente é defeito da regra, não do portal.
const defects = cases.filter((item) => item.outcome !== "ausente_da_lista");
const result = {
  check_version: CHECK_VERSION,
  read_at: readAt,
  portal_contracts: contracts.length,
  pages,
  counts,
  decision: defects.length === 0 ? "approved" : "changes_requested",
  cases,
};
await writeFile(outputPath, JSON.stringify(result, null, 2));
console.log(`${contracts.length} contratos lidos em ${pages.length} páginas; ` +
  `${JSON.stringify(counts)}; decisão sugerida: ${result.decision}`);
for (const item of defects) {
  console.log(`  #${item.order} ${item.cited_number} ${item.creditor_name}: ${item.outcome}`);
}
