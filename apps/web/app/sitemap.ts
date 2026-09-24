import type { MetadataRoute } from "next";

import { getPublicFinanceCoverage } from "../lib/finance-coverage";
import { searchMunicipalControlDocuments } from "../lib/municipal-control-documents";
import { getPublicPayrollMonths } from "../lib/public-payroll.mjs";
import { getPublicSitemapEntries } from "../lib/sitemap-entries";

const BASE_URL = "https://barreiras-em-dados.vercel.app";

const ENTRY_PATHS = {
  diario_edicao: (key: string) => `/diario/${key}`,
  contratacao: (key: string) => `/licitacoes/contratacao/${encodeURIComponent(key)}`,
  fornecedor: (key: string) => `/licitacoes/fornecedor/${key}`,
} as const;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [legalDocuments, entries, financeCoverage, payrollMonths] =
    await Promise.all([
      searchMunicipalControlDocuments({ pageSize: 50 }),
      getPublicSitemapEntries(),
      getPublicFinanceCoverage(),
      getPublicPayrollMonths(120),
    ]);
  const staticRoutes = [
    { route: "", changeFrequency: "daily", priority: 1 },
    { route: "/diario", changeFrequency: "daily", priority: 0.9 },
    { route: "/atos", changeFrequency: "daily", priority: 0.9 },
    { route: "/financas", changeFrequency: "daily", priority: 0.9 },
    { route: "/financas/cobertura", changeFrequency: "daily", priority: 0.8 },
    { route: "/financas/base-legal", changeFrequency: "daily", priority: 0.8 },
    { route: "/licitacoes", changeFrequency: "daily", priority: 0.9 },
    { route: "/recursos", changeFrequency: "daily", priority: 0.9 },
    { route: "/recursos/saude", changeFrequency: "weekly", priority: 0.7 },
    { route: "/representantes", changeFrequency: "weekly", priority: 0.8 },
    { route: "/camara", changeFrequency: "daily", priority: 0.8 },
    { route: "/estado", changeFrequency: "daily", priority: 0.7 },
    { route: "/sobre", changeFrequency: "monthly", priority: 0.5 },
  ].map((entry) => ({
    url: `${BASE_URL}${entry.route}`,
    changeFrequency: entry.changeFrequency as "daily" | "weekly" | "monthly",
    priority: entry.priority,
  }));

  const detailRoutes: MetadataRoute.Sitemap = legalDocuments.state === "available"
    ? legalDocuments.documents.map((document) => ({
        url: `${BASE_URL}/financas/base-legal/${document.documentId}`,
        changeFrequency: "monthly",
        priority: 0.6,
        lastModified: new Date(document.collectedAt),
      }))
    : [];

  const ownPages: MetadataRoute.Sitemap = entries.map((entry) => ({
    url: `${BASE_URL}${ENTRY_PATHS[entry.kind](entry.key)}`,
    changeFrequency: "monthly",
    priority: entry.kind === "fornecedor" ? 0.5 : 0.6,
    lastModified: new Date(entry.lastModified),
  }));

  // Só meses com receita e despesa publicadas; lacuna não vira página indexada.
  const financeMonths: MetadataRoute.Sitemap =
    financeCoverage.state === "available"
      ? financeCoverage.rows
          .filter((row) => row.coverageStatus === "complete")
          .map((row) => ({
            url: `${BASE_URL}/financas/${row.periodStart.slice(0, 7)}`,
            changeFrequency: "monthly" as const,
            priority: 0.6,
          }))
      : [];

  // Só meses com folha publicada; mês ausente não vira página indexada.
  const payrollPages: MetadataRoute.Sitemap =
    payrollMonths.state === "available"
      ? payrollMonths.months.map((month) => ({
          url: `${BASE_URL}/financas/folha/${month.referenceMonth.slice(0, 7)}`,
          changeFrequency: "monthly" as const,
          priority: 0.6,
        }))
      : [];

  return [
    ...staticRoutes,
    ...detailRoutes,
    ...financeMonths,
    ...payrollPages,
    ...ownPages,
  ];
}
