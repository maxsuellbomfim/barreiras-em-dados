import type { MetadataRoute } from "next";

const BASE_URL = "https://barreiras-em-dados.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { route: "", changeFrequency: "daily", priority: 1 },
    { route: "/diario", changeFrequency: "daily", priority: 0.9 },
    { route: "/atos", changeFrequency: "daily", priority: 0.9 },
    { route: "/financas", changeFrequency: "daily", priority: 0.9 },
    { route: "/licitacoes", changeFrequency: "daily", priority: 0.9 },
    { route: "/recursos", changeFrequency: "daily", priority: 0.9 },
    { route: "/representantes", changeFrequency: "weekly", priority: 0.8 },
    { route: "/camara", changeFrequency: "daily", priority: 0.8 },
    { route: "/sobre", changeFrequency: "monthly", priority: 0.5 },
  ].map((entry) => ({
    url: `${BASE_URL}${entry.route}`,
    changeFrequency: entry.changeFrequency as "daily" | "weekly" | "monthly",
    priority: entry.priority,
  }));
}
