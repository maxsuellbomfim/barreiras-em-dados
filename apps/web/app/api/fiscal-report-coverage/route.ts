import { getPublicFinanceDocuments } from "../../../lib/finance-documents";
import {
  toFiscalCoverageEntry,
  type FiscalReportCoverageEntry,
  type FiscalReportCoverageResult,
} from "../../../lib/fiscal-report-coverage-matrix.mjs";

export const dynamic = "force-dynamic";
export const revalidate = 0;

async function loadCoverage(): Promise<FiscalReportCoverageResult> {
  const [rreo, rgf] = await Promise.all([
    getPublicFinanceDocuments("rreo"),
    getPublicFinanceDocuments("rgf"),
  ]);
  if (rreo.state !== "available" || rgf.state !== "available") {
    return { state: "unavailable" };
  }
  const entries: FiscalReportCoverageEntry[] = [];
  for (const document of [...rreo.documents, ...rgf.documents]) {
    if (document.fiscalYear !== null && document.fiscalYear < 2021) continue;
    const entry = toFiscalCoverageEntry(document);
    if (!entry) return { state: "unavailable" };
    entries.push(entry);
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
