import type { MetadataRoute } from "next";

import { searchMunicipalControlDocuments } from "../lib/municipal-control-documents";

const BASE_URL = "https://barreiras-em-dados.vercel.app";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const legalDocuments = await searchMunicipalControlDocuments({ pageSize: 50 });
  const staticRoutes = [
    { route: "", changeFrequency: "daily", priority: 1 },
    { route: "/diario", changeFrequency: "daily", priority: 0.9 },
    { route: "/atos", changeFrequency: "daily", priority: 0.9 },
    { route: "/financas", changeFrequency: "daily", priority: 0.9 },
    { route: "/financas/base-legal", changeFrequency: "daily", priority: 0.8 },
    { route: "/licitacoes", changeFrequency: "daily", priority: 0.9 },
    { route: "/recursos", changeFrequency: "daily", priority: 0.9 },
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

  return [...staticRoutes, ...detailRoutes];
}
