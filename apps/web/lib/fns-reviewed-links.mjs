const CODE = /^257001\d{9}OB\d{6}$/;
const SHA = /^[0-9a-f]{64}$/;
const SOURCE = "https://consultafns.saude.gov.br/#/detalhada";
const METHOD = "fns-cgu-reviewed-links/1.0.0";
const unavailable = () => ({ state: "unavailable", links: [] });

export async function loadReviewedFnsLinks(documents, callRpc) {
  if (!Array.isArray(documents) || documents.length > 50) return unavailable();
  const counts = new Map();
  for (const doc of documents) counts.set(doc.documentCode, (counts.get(doc.documentCode) ?? 0) + 1);
  const eligible = new Map(documents.filter((doc) =>
    doc.expenseStage === "payment" && doc.authorKind === "commission" &&
    doc.authorName === "COM. DA SAUDE" && CODE.test(doc.documentCode) &&
    SHA.test(doc.artifactSha256) && counts.get(doc.documentCode) === 1
  ).map((doc) => [doc.documentCode, doc.artifactSha256]));
  if (eligible.size === 0) return { state: "available", links: [] };
  try {
    const rows = await callRpc([...eligible.keys()]);
    if (!Array.isArray(rows) || rows.length > eligible.size) return unavailable();
    const seen = new Set();
    const links = [];
    for (const row of rows) {
      if (!row || typeof row !== "object" || !eligible.has(row.document_code) ||
          seen.has(row.document_code) || !SHA.test(row.cgu_archive_sha256) ||
          !SHA.test(row.payment_sha256) || !SHA.test(row.order_sha256) ||
          row.fns_author_name !== "COMISSÃO DA SAÚDE" ||
          typeof row.requester_name !== "string" ||
          !/^[\p{L}][\p{L} '-]{1,119}$/u.test(row.requester_name) ||
          row.requester_name.trim() !== row.requester_name ||
          typeof row.reviewed_at !== "string" || !Number.isFinite(Date.parse(row.reviewed_at)) ||
          row.source_url !== SOURCE || row.methodology_version !== METHOD) return unavailable();
      seen.add(row.document_code);
      // CGU cards can come from a cached snapshot. Never attach a newer review
      // to an older card, even when the short document code still matches.
      if (eligible.get(row.document_code) !== row.cgu_archive_sha256) continue;
      links.push({
        documentCode: row.document_code,
        cguArchiveSha256: row.cgu_archive_sha256,
        requesterName: row.requester_name,
        fnsAuthorName: row.fns_author_name,
        paymentSha256: row.payment_sha256,
        orderSha256: row.order_sha256,
        sourceUrl: SOURCE,
        reviewedAt: row.reviewed_at,
      });
    }
    return { state: "available", links };
  } catch {
    return unavailable();
  }
}
