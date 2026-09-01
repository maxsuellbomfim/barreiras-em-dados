import type { FinanceFamilyCoverage } from "../../lib/finance-family-coverage.mjs";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatPeriod(value: string | null): string {
  if (!value) return "nenhum período publicado";
  if (/^\d{4}$/.test(value)) return value;
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00-03:00`);
  return Number.isNaN(parsed.getTime()) ? value : monthFormatter.format(parsed);
}

function statusLabel(family: FinanceFamilyCoverage): string {
  if (family.state === "unavailable") return "Fonte ainda indisponível";
  if (family.classifiedPeriods === null) {
    return `${family.observedPeriods.toLocaleString("pt-BR")} período${family.observedPeriods === 1 ? "" : "s"} observado${family.observedPeriods === 1 ? "" : "s"}`;
  }
  if (family.gapPeriods === 0) return "Sem lacuna classificada";
  return `${family.gapPeriods?.toLocaleString("pt-BR")} lacuna${family.gapPeriods === 1 ? "" : "s"} explicada${family.gapPeriods === 1 ? "" : "s"}`;
}

function coverageCopy(family: FinanceFamilyCoverage): string {
  if (family.classifiedPeriods === null) {
    return family.observedPeriods === 0
      ? "Ainda não há período preservado nesta projeção. Isso não significa valor zero."
      : "A contagem mostra documentos observados; a cobertura esperada desta cadência ainda não foi classificada."
  }
  if (family.classifiedPeriods === 0) {
    return "A série ainda não retornou competências classificadas. Isso não significa valor zero."
  }
  return `${family.observedPeriods.toLocaleString("pt-BR")} de ${family.classifiedPeriods.toLocaleString("pt-BR")} competências têm publicação validada.`;
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
          precisa, mas seria enganosa.
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
