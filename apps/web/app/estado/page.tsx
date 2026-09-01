import type { Metadata } from "next";

import type { OperationalHealth } from "../../lib/operational-health.mjs";
import { getOperationalHealthSnapshot } from "../../lib/operational-health-snapshot";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Estado das fontes",
  description:
    "Disponibilidade atual das principais projeções públicas do Barreiras 360, sem confundir falha, vazio e cobertura histórica.",
};

type HealthCheck = OperationalHealth["checks"][number];

const destinations: Record<HealthCheck["key"], Readonly<{
  href: string;
  description: string;
}>> = {
  diary: {
    href: "/diario",
    description: "Edições e documentos preservados do Diário Oficial.",
  },
  finance: {
    href: "/financas",
    description: "Receitas, despesas e fechamentos publicados com evidência.",
  },
  representatives: {
    href: "/representantes",
    description: "Executivo, Câmara e representação territorial publicada.",
  },
};

function statusText(status: HealthCheck["status"]): string {
  if (status === "available") return "Dados disponíveis agora";
  if (status === "empty") return "Fonte consultada, sem registros neste recorte";
  return "Consulta indisponível agora";
}

function summaryText(status: OperationalHealth["status"]): string {
  if (status === "ok") {
    return "As três áreas públicas consultadas responderam com dados.";
  }
  if (status === "degraded") {
    return "Parte das áreas públicas respondeu; as demais estão identificadas abaixo.";
  }
  return "Nenhuma das três áreas pôde ser consultada neste momento.";
}

const checkedAtFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "America/Bahia",
});

export default async function PublicSourceStatusPage() {
  const health = await getOperationalHealthSnapshot();

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/">← Barreiras 360</a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/diario">Diário</a>
            <a href="/financas">Finanças</a>
            <a href="/representantes">Quem decide</a>
          </nav>
        </div>
      </header>

      <section className="section source-status-page" aria-labelledby="source-status-title">
        <div className="source-status-intro">
          <span className="eyebrow">Transparência da própria plataforma</span>
          <h1 id="source-status-title">Estado das fontes</h1>
          <p>
            {summaryText(health.status)} Esta fotografia confirma se as projeções
            públicas respondem agora; ela não mede a cobertura histórica completa
            nem substitui a evidência de cada página.
          </p>
          <p className="source-status-checked-at">
            Verificado em{" "}
            <time dateTime={health.checkedAt}>
              {checkedAtFormatter.format(new Date(health.checkedAt))}
            </time>
            , no horário de Barreiras.
          </p>
        </div>

        <div className="source-status-grid">
          {health.checks.map((check) => {
            const destination = destinations[check.key];
            return (
              <article
                className="source-status-card"
                data-status={check.status}
                key={check.key}
              >
                <div>
                  <span className="source-status-label">
                    {statusText(check.status)}
                  </span>
                  <h2>{check.label}</h2>
                  <p>{destination.description}</p>
                </div>
                {check.records === null ? (
                  <p className="source-status-note">
                    A ausência de contagem significa falha de consulta, não zero.
                  </p>
                ) : (
                  <p className="source-status-note">
                    {check.records.toLocaleString("pt-BR")} registro
                    {check.records === 1 ? "" : "s"} devolvido
                    {check.records === 1 ? "" : "s"} nesta consulta. Isso não é
                    uma contagem de todo o histórico.
                  </p>
                )}
                <a className="source-status-link" href={destination.href}>
                  Conferir os dados
                </a>
              </article>
            );
          })}
        </div>

        <aside className="source-status-method" aria-labelledby="source-status-method-title">
          <h2 id="source-status-method-title">Como interpretar</h2>
          <dl>
            <div>
              <dt>Disponível</dt>
              <dd>A projeção pública respondeu com pelo menos um registro válido.</dd>
            </div>
            <div>
              <dt>Sem registros neste recorte</dt>
              <dd>A consulta funcionou e devolveu uma lista vazia; isso não prova ausência histórica.</dd>
            </div>
            <div>
              <dt>Indisponível</dt>
              <dd>A consulta falhou ou não pôde ser validada; nenhum zero é presumido.</dd>
            </div>
          </dl>
        </aside>
      </section>
    </main>
  );
}
