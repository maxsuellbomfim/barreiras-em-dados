import {
  getPublicFinanceDocuments,
  type FinanceDocumentsResult,
} from "./finance-documents";
import {
  toFiscalCoverageEntry,
  type FiscalReportCoverageEntry,
  type FiscalReportCoverageResult,
} from "./fiscal-report-coverage-matrix.mjs";
import {
  toMunicipalFinanceDocumentCoverageEntry,
  type MunicipalFinanceDocumentCoverageEntry,
  type MunicipalFinanceDocumentCoverageResult,
} from "./municipal-finance-document-coverage.mjs";

export function buildFiscalReportCoverageResult(
  rreo: FinanceDocumentsResult,
  rgf: FinanceDocumentsResult,
): FiscalReportCoverageResult {
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

export function buildMunicipalFinanceDocumentCoverageResult(
  results: readonly FinanceDocumentsResult[],
): MunicipalFinanceDocumentCoverageResult {
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

export async function getPublicFiscalReportCoverageResult(): Promise<FiscalReportCoverageResult> {
  const [rreo, rgf] = await Promise.all([
    getPublicFinanceDocuments("rreo"),
    getPublicFinanceDocuments("rgf"),
  ]);
  return buildFiscalReportCoverageResult(rreo, rgf);
}

export async function getPublicMunicipalFinanceDocumentCoverageResult(): Promise<MunicipalFinanceDocumentCoverageResult> {
  const results = await Promise.all([
    getPublicFinanceDocuments("balancetes"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-receita"),
    getPublicFinanceDocuments("pdc-resumo-execucao-da-despesa"),
  ]);
  return buildMunicipalFinanceDocumentCoverageResult(results);
}
