import { getPublicFinanceDocuments } from "../../../lib/finance-documents";
import {
  toMunicipalFinanceDocumentCoverageEntry,
  type MunicipalFinanceDocumentCoverageEntry,
  type MunicipalFinanceDocumentCoverageResult,
} from "../../../lib/municipal-finance-document-coverage.mjs";

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function loadCoverage(): Promise<MunicipalFinanceDocumentCoverageResult> {
  const results = await Promise.all([
    getPublicFinanceDocuments("balancetes"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-receita"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-despesa"),
  ]);
  if (results.some((result) => result.state !== "available")) {
    return { state: "unavailable" };
  }

  const entries: MunicipalFinanceDocumentCoverageEntry[] = [];
  for (const result of results) {
    if (result.state !== "available") return { state: "unavailable" };
    for (const document of result.documents) {
      if (document.fiscalYear !== null && document.fiscalYear < 2021) continue;
      const entry = toMunicipalFinanceDocumentCoverageEntry(document);
      if (!entry) return { state: "unavailable" };
      entries.push(entry);
    }
  }
  return { state: "available", entries };
}

export async function GET(): Promise<Response> {
  const result = await loadCoverage();
  return Response.json(result, {
    status: result.state === "available" ? 200 : 503,
    headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
  });
}
