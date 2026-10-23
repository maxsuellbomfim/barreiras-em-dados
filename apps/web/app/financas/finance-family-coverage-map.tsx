import type { FinanceFamilyCoverage } from "../../lib/finance-family-coverage.mjs";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatPeriod(value: string | null): string {
  if (!value) return "não identificado nesta consulta";
  if (/^\d{4}$/.test(value)) return value;
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : monthFormatter.format(parsed);
}

function statusLabel(family: FinanceFamilyCoverage): string {
  if (family.state === "unavailable") return "Cobertura não disponível nesta consulta";
  if (family.classifiedPeriods === null) {
    return `${family.observedPeriods.toLocaleString("pt-BR")} referência${family.observedPeriods === 1 ? "" : "s"} no recorte consultado`;
  }
  if (family.gapPeriods === 0) return "Sem lacunas no recorte consultado";
  return `${family.gapPeriods?.toLocaleString("pt-BR")} ${family.gapPeriods === 1 ? "registro mensal sem publicação validada" : "registros mensais sem publicação validada"} no recorte consultado`;
}

function coverageCopy(family: FinanceFamilyCoverage): string {
  if (family.classifiedPeriods === null) {
    return family.observedPeriods === 0
      ? "Não foi possível apurar períodos nesta consulta. Isso não significa valor zero nem ausência de documentos na fonte."
      : "Referências distintas por tipo de relatório e período nesta consulta limitada; não é o total do acervo."
  }
  if (family.classifiedPeriods === 0) {
    return "A série ainda não retornou meses classificados. Isso não significa valor zero."
  }
  return `${family.observedPeriods.toLocaleString("pt-BR")} de ${family.classifiedPeriods.toLocaleString("pt-BR")} registros mensais consultados têm publicação validada. Cada órgão e mês conta separadamente.`;
}

export default function FinanceFamilyCoverageMap({
  families,
}: Readonly<{ families: readonly FinanceFamilyCoverage[] }>) {
  return (
    <section className="finance-family-map" aria-labelledby="finance-family-map-title">
      <div className="section-heading compact">
        <span className="eyebrow">Mapa das fontes</span>
        <h2 id="finance-family-map-title">O que já pode ser conferido — e em qual ritmo</h2>
        <p>
          Cada fonte tem uma periodicidade própria. Por isso, o portal não mistura
          meses, bimestres, quadrimestres e anos numa porcentagem única que pareceria
          precisa, mas seria enganosa. O recorte consultado não comprova cobertura histórica completa.
        </p>
      </div>
      <ul className="finance-family-map-list">
        {families.map((family) => (
          <li data-state={family.state} key={family.key}>
            <div className="finance-family-map-heading">
              <div>
                <span>{family.cadence}</span>
                <h3>{family.title}</h3>
              </div>
              <strong>{statusLabel(family)}</strong>
            </div>
            <p>{coverageCopy(family)}</p>
            <div className="finance-family-map-meta">
              <span>Último período observado: {formatPeriod(family.latestObservedPeriod)}</span>
              {family.state === "unavailable" ? (
                <span>Aguardando cobertura verificável</span>
              ) : (
                <a href={family.href}>Ver série e evidências ↓</a>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="finance-family-map-note">
        “Documento não localizado”, “processamento pendente” e “divergência entre
        fontes” permanecem lacunas explícitas. Nenhum desses estados é convertido em R$ 0.
      </p>
    </section>
  );
}
