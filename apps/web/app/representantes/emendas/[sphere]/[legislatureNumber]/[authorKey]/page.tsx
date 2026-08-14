import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  getPublicParliamentaryContributionProfile,
  PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE,
} from "../../../../../../lib/parliamentary-contribution-profiles";
import type {
  ParliamentaryContributionProfile,
  ParliamentaryContributionRow,
  ParliamentaryContributionSphere,
} from "../../../../../../lib/parliamentary-contribution-profile.mjs";
import { formatBrlDecimal } from "../../../../../../lib/revenues";

export const revalidate = 300;

type PageProps = Readonly<{
  params: Promise<{
    sphere: string;
    legislatureNumber: string;
    authorKey: string;
  }>;
  searchParams: Promise<{ pagina?: string | string[] }>;
}>;

function parseRoute(
  sphereValue: string,
  legislatureValue: string,
  authorKeyValue: string,
) {
  if (sphereValue !== "federal" && sphereValue !== "state") return null;
  if (!/^\d{1,3}$/u.test(legislatureValue)) return null;
  const legislatureNumber = Number(legislatureValue);
  const authorKey = authorKeyValue.trim();
  if (!authorKey || authorKey.length > 200 || /[\u0000-\u001f\u007f]/u.test(authorKey)) {
    return null;
  }
  return {
    sphere: sphereValue as ParliamentaryContributionSphere,
    legislatureNumber,
    authorKey,
  };
}

function parsePage(value: string | string[] | undefined): number | null {
  if (value === undefined) return 1;
  if (Array.isArray(value) || !/^\d{1,3}$/u.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 1 && page <= 401 ? page : null;
}

function amount(value: string | null): string {
  return value === null
    ? "não localizado na fonte consultada"
    : formatBrlDecimal(value);
}

function sphereLabel(sphere: ParliamentaryContributionSphere): string {
  return sphere === "federal" ? "Câmara dos Deputados" : "Assembleia Legislativa da Bahia";
}

function rankingStageLabel(profile: ParliamentaryContributionProfile): string {
  return profile.rankingAmountStage === "destination"
    ? "Destinado a Barreiras"
    : "Autorizado na LOA para Barreiras";
}

function statusCopy(status: string): string {
  const labels: Record<string, string> = {
    matched_exact: "registro atual e histórico conferem",
    current_only: "localizado somente na fonte operacional atual",
    historical_only: "localizado somente no arquivo histórico",
    execution_confirmed: "execução ligada por chave oficial única",
    ambiguous_official_key: "execução não atribuída: chave oficial ambígua",
    not_found_in_execution_source: "execução não localizada na fonte consultada",
    official_link_key_unavailable: "a fonte não publicou chave suficiente para ligar a execução",
    scope_not_available: "execução territorial ainda indisponível neste recorte",
  };
  return labels[status] ?? "situação documental não classificada";
}

function shortHash(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}

function ContributionCard({
  row,
  profile,
}: Readonly<{
  row: ParliamentaryContributionRow;
  profile: ParliamentaryContributionProfile;
}>) {
  return (
    <article className="parliamentary-contribution-card">
      <div className="parliamentary-contribution-heading">
        <div>
          <span className="eyebrow">Exercício {row.fiscalYear}</span>
          <h2>
            {row.amendmentNumber
              ? `Emenda ${row.amendmentNumber}`
              : "Registro sem número de emenda publicado"}
          </h2>
        </div>
        <span className="parliamentary-contribution-status">
          {statusCopy(row.executionStatus)}
        </span>
      </div>

      <p className="parliamentary-contribution-object">
        {row.objectDescription ?? "Objeto não informado na fonte consultada."}
      </p>
      {row.beneficiaryName ? (
        <p className="parliamentary-contribution-beneficiary">
          <strong>Beneficiário publicado:</strong> {row.beneficiaryName}
        </p>
      ) : null}

      <dl className="parliamentary-contribution-values">
        <div>
          <dt>{rankingStageLabel(profile)}</dt>
          <dd>{formatBrlDecimal(row.rankingAmount)}</dd>
        </div>
        <div>
          <dt>Empenhado localizado</dt>
          <dd>{amount(row.committedAmount)}</dd>
        </div>
        <div>
          <dt>Liquidado localizado</dt>
          <dd>
            {profile.sphere === "federal"
              ? "não publicado neste recorte federal"
              : amount(row.liquidatedAmount)}
          </dd>
        </div>
        <div>
          <dt>Pago localizado</dt>
          <dd>{amount(row.paidAmount)}</dd>
        </div>
      </dl>

      <details className="parliamentary-contribution-evidence">
        <summary>Conferir documentos e rastreabilidade</summary>
        <div>
          {row.evidenceExcerpt ? (
            <blockquote>
              {row.evidenceExcerpt}
              {row.pageNumber ? <cite>Página {row.pageNumber}</cite> : null}
            </blockquote>
          ) : null}
          <p>
            <a href={row.primarySourceUrl} target="_blank" rel="noreferrer">
              Abrir fonte oficial principal ↗
            </a>
            <br />
            <span>SHA-256: <code>{shortHash(row.primaryArtifactSha256)}</code></span>
          </p>
          {row.secondarySourceUrl && row.secondaryArtifactSha256 ? (
            <p>
              <a href={row.secondarySourceUrl} target="_blank" rel="noreferrer">
                Abrir segunda fonte usada na conferência ↗
              </a>
              <br />
              <span>SHA-256: <code>{shortHash(row.secondaryArtifactSha256)}</code></span>
            </p>
          ) : null}
          <p><strong>Chave auditável:</strong> <code>{row.contributionKey}</code></p>
        </div>
      </details>
    </article>
  );
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const route = await params;
  const parsed = parseRoute(route.sphere, route.legislatureNumber, route.authorKey);
  if (!parsed) return { title: "Perfil de emendas inválido | Barreiras 360" };
  return {
    title: `Emendas de ${parsed.authorKey} | Barreiras 360`,
    description: "Emendas destinadas ou autorizadas para Barreiras, separadas por estágio financeiro e sustentadas por fontes oficiais.",
  };
}

export default async function ParliamentaryContributionProfilePage({
  params,
  searchParams,
}: PageProps) {
  const routeParams = await params;
  const route = parseRoute(
    routeParams.sphere,
    routeParams.legislatureNumber,
    routeParams.authorKey,
  );
  const query = await searchParams;
  const page = parsePage(query.pagina);
  if (!route || page === null) notFound();

  const result = await getPublicParliamentaryContributionProfile({ ...route, page });

  if (result.state !== "available") {
    return (
      <main>
        <header className="site-header">
          <div className="nav-shell">
            <a className="brand" href="/representantes#emendas-por-legislatura">
              <span>← Emendas por legislatura</span>
            </a>
          </div>
        </header>
        <section className="section parliamentary-contribution-empty">
          <span className="eyebrow">Rastro do recurso</span>
          <h1>
            {result.state === "not_found"
              ? "Nenhuma contribuição encontrada neste recorte"
              : "Consulta temporariamente indisponível"}
          </h1>
          <p>
            {result.state === "not_found"
              ? "Isso não significa valor zero nem ausência de atuação. A fonte consultada não devolveu registros para esta autoria, legislatura e página."
              : "Nenhum valor será estimado ou substituído por zero enquanto a consulta oficial estiver indisponível."}
          </p>
        </section>
      </main>
    );
  }

  const { profile } = result;
  const totalPages = Math.ceil(
    profile.totalAmendmentCount / PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE,
  );

  return (
    <main>
      <header className="site-header">
        <div className="nav-shell">
          <a className="brand" href="/representantes#emendas-por-legislatura">
            <span>← Emendas por legislatura</span>
          </a>
          <nav className="nav-links" aria-label="Páginas públicas">
            <a href="/recursos">Recursos</a>
            <a href="/financas">Finanças</a>
          </nav>
        </div>
      </header>

      <section className="section parliamentary-contribution-profile" aria-labelledby="contribution-title">
        <div className="section-heading">
          <span className="eyebrow">{sphereLabel(profile.sphere)}</span>
          <h1 id="contribution-title">Emendas de {profile.authorName}</h1>
          <p>
            {profile.legislatureLabel}, de {profile.fullFiscalYearFrom} a{" "}
            {profile.fullFiscalYearTo}. Os valores abaixo são calculados por SQL
            determinístico e mantêm cada estágio financeiro separado.
          </p>
        </div>

        <div className="parliamentary-contribution-warning" role="note">
          <strong>O que este perfil mede</strong>
          <p>
            Somente emendas para Barreiras encontradas nas fontes cobertas. Não
            é uma nota geral de desempenho, e valor destinado ou autorizado não
            significa dinheiro pago ou obra executada.
          </p>
        </div>

        <dl className="parliamentary-contribution-totals">
          <div>
            <dt>{rankingStageLabel(profile)}</dt>
            <dd>{formatBrlDecimal(profile.totalRankingAmount)}</dd>
          </div>
          <div>
            <dt>Empenhado localizado</dt>
            <dd>{amount(profile.totalCommittedAmount)}</dd>
          </div>
          <div>
            <dt>Liquidado localizado</dt>
            <dd>
              {profile.sphere === "federal"
                ? "não publicado neste recorte federal"
                : amount(profile.totalLiquidatedAmount)}
            </dd>
          </div>
          <div>
            <dt>Pago localizado</dt>
            <dd>{amount(profile.totalPaidAmount)}</dd>
          </div>
        </dl>

        <div className="parliamentary-contribution-list-heading">
          <div>
            <span className="eyebrow">Emenda por emenda</span>
            <h2>{profile.totalAmendmentCount.toLocaleString("pt-BR")} registro(s) no recorte</h2>
          </div>
          <span>Página {page} de {totalPages}</span>
        </div>

        <div className="parliamentary-contribution-list">
          {profile.contributions.map((row) => (
            <ContributionCard key={row.contributionKey} profile={profile} row={row} />
          ))}
        </div>

        {totalPages > 1 ? (
          <nav className="parliamentary-contribution-pagination" aria-label="Paginar emendas">
            {page > 1 ? <a href={`?pagina=${page - 1}`}>← Página anterior</a> : <span />}
            {page < totalPages ? <a href={`?pagina=${page + 1}`}>Próxima página →</a> : null}
          </nav>
        ) : null}

        <details className="parliamentary-contribution-methodology">
          <summary>Período, fonte e limites deste recorte</summary>
          <div>
            <p>{profile.officialSourceNote}</p>
            {profile.excludedTransitionYears.length > 0 ? (
              <p>
                Ano(s) de transição excluído(s):{" "}
                {profile.excludedTransitionYears.join(", ")}. As fontes não
                publicam data individual suficiente para atribuir todo o ano a
                uma única legislatura.
              </p>
            ) : null}
            <p>
              Campo ausente significa “não localizado na fonte consultada”;
              nunca é convertido em R$ 0,00.
            </p>
            <a href={profile.officialSourceUrl} target="_blank" rel="noreferrer">
              Conferir fonte oficial da legislatura ↗
            </a>
            {profile.representativeProfileUrl ? (
              <a href={profile.representativeProfileUrl} target="_blank" rel="noreferrer">
                Abrir perfil oficial atual ↗
              </a>
            ) : null}
          </div>
        </details>
      </section>
    </main>
  );
}
