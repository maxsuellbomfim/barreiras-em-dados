import { formatBrlDecimal } from "../../lib/revenues";
import type {
  ParliamentaryLegislatureRankingGroup,
  ParliamentaryLegislatureRankingRow,
} from "../../lib/parliamentary-legislature-rankings.mjs";
import type { ParliamentaryLegislatureCoverageRow } from
  "../../lib/parliamentary-legislature-coverage.mjs";

function stageLabel(group: ParliamentaryLegislatureRankingGroup): string {
  return group.rankingAmountStage === "destination"
    ? "Valor destinado a Barreiras"
    : "Valor autorizado na LOA para Barreiras";
}

function formatOfficialDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function financialValue(value: string | null): string {
  return value === null ? "não encontrado na fonte" : formatBrlDecimal(value);
}

function LegislatureRankingRow({
  row,
  group,
}: Readonly<{
  row: ParliamentaryLegislatureRankingRow;
  group: ParliamentaryLegislatureRankingGroup;
}>) {
  if (
    row.rankPosition === null || row.authorName === null ||
    row.authorKey === null || row.amendmentCount === null ||
    row.rankingAmount === null
  ) return null;
  return (
    <article className="legislature-ranking-row">
      <span className="transfer-rank" aria-label={`${row.rankPosition}º lugar`}>
        {row.rankPosition}º
      </span>
      <div className="legislature-ranking-person">
        <h4>{row.authorName}</h4>
        <p>
          {row.amendmentCount.toLocaleString("pt-BR")} emenda(s) encontrada(s)
          {row.firstYear === row.lastYear
            ? ` em ${row.firstYear}`
            : ` entre ${row.firstYear} e ${row.lastYear}`}
        </p>
        {row.representativeProfileUrl ? (
          <a href={row.representativeProfileUrl} target="_blank" rel="noreferrer">
            Perfil oficial atual →
          </a>
        ) : (
          <span>Perfil atual ainda não associado à autoria histórica</span>
        )}
        <a
          className="legislature-ranking-detail-link"
          href={`/representantes/emendas/${group.sphere}/${group.legislatureNumber}/${encodeURIComponent(row.authorKey)}`}
        >
          Ver emendas, valores e documentos →
        </a>
      </div>
      <dl className="legislature-ranking-values">
        <div>
          <dt>{stageLabel(group)}</dt>
          <dd>{formatBrlDecimal(row.rankingAmount)}</dd>
        </div>
        <div>
          <dt>Empenhado localizado</dt>
          <dd>{financialValue(row.committedAmount)}</dd>
        </div>
        <div>
          <dt>Liquidado localizado</dt>
          <dd>
            {group.sphere === "federal"
              ? "não publicado neste recorte"
              : financialValue(row.liquidatedAmount)}
          </dd>
        </div>
        <div>
          <dt>Pagamento localizado</dt>
          <dd>{financialValue(row.paidAmount)}</dd>
        </div>
      </dl>
    </article>
  );
}

function CoverageSummary({
  coverage,
}: Readonly<{ coverage: ParliamentaryLegislatureCoverageRow | null }>) {
  if (coverage === null) {
    return (
      <p className="legislature-coverage-unavailable">
        Diagnóstico de cobertura indisponível nesta consulta. O ranking não deve
        ser interpretado como acervo completo.
      </p>
    );
  }
  return (
    <div className="legislature-coverage" role="note">
      <strong>O que esta fonte permitiu conferir neste recorte</strong>
      <dl>
        <div>
          <dt>Emendas encontradas</dt>
          <dd>{coverage.contributionCount.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Autores identificados</dt>
          <dd>
            {coverage.authorCount.toLocaleString("pt-BR")} · {coverage.linkedAuthorCount.toLocaleString("pt-BR")} ligados a perfil oficial
          </dd>
        </div>
        <div>
          <dt>Objeto informado</dt>
          <dd>{coverage.withObjectCount.toLocaleString("pt-BR")} de {coverage.contributionCount.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Beneficiário informado</dt>
          <dd>
            {coverage.withBeneficiaryCount === null
              ? "campo não publicado nesta fonte"
              : `${coverage.withBeneficiaryCount.toLocaleString("pt-BR")} de ${coverage.contributionCount.toLocaleString("pt-BR")}`}
          </dd>
        </div>
        <div>
          <dt>Execução ligada com segurança</dt>
          <dd>{coverage.executionConfirmedCount.toLocaleString("pt-BR")} de {coverage.contributionCount.toLocaleString("pt-BR")}</dd>
        </div>
        <div>
          <dt>Com evidência oficial preservada</dt>
          <dd>{coverage.primaryEvidenceCount.toLocaleString("pt-BR")} de {coverage.contributionCount.toLocaleString("pt-BR")}</dd>
        </div>
      </dl>
      <p>
        Estes números descrevem a cobertura observada nas fontes já coletadas;
        não provam que o universo oficial esteja completo.
      </p>
    </div>
  );
}

export default function LegislatureTransferRankings({
  groups,
  coverage,
}: Readonly<{
  groups: readonly ParliamentaryLegislatureRankingGroup[] | null;
  coverage: readonly ParliamentaryLegislatureCoverageRow[] | null;
}>) {
  return (
    <section
      id="emendas-por-legislatura"
      className="representation-block representation-legislature-rankings"
      aria-labelledby="legislature-rankings-title"
    >
      <div className="section-heading">
        <span className="eyebrow">Recursos destinados ao município</span>
        <h2 id="legislature-rankings-title">
          Quem mais destinou emendas a Barreiras, por legislatura
        </h2>
        <p>
          Estadual e federal aparecem separados. A ordem usa o valor oficial
          destinado ou autorizado; pagamento é outro estágio e nunca altera a
          posição deste ranking.
        </p>
      </div>

      {groups === null ? (
        <div className="collection-unavailable" role="status">
          <div>
            <strong>Ranking por legislatura temporariamente indisponível</strong>
            <p>
              Isso indica falha de consulta ou migration ainda não aplicada —
              não significa ausência de emendas para Barreiras.
            </p>
          </div>
        </div>
      ) : (
        <div className="legislature-ranking-groups">
          {groups.map((group) => {
            const today = new Date().toISOString().slice(0, 10);
            const current = group.beginsOn <= today && group.endsOn >= today;
            const groupCoverage = coverage?.find((row) =>
              row.sphere === group.sphere &&
              row.legislatureNumber === group.legislatureNumber
            ) ?? null;
            return (
              <details
                className="legislature-ranking-group"
                key={`${group.sphere}:${group.legislatureNumber}`}
                open={current}
              >
                <summary>
                  <span>
                    <strong>{group.legislatureLabel}</strong>
                    <small>
                      período: {formatOfficialDate(group.beginsOn)} a{" "}
                      {formatOfficialDate(group.endsOn)} · anos completos usados:{" "}
                      {group.fullFiscalYearFrom}–{group.fullFiscalYearTo}
                    </small>
                  </span>
                  <span>
                    {group.rankings.length === 0
                      ? "sem registros no recorte"
                      : `${group.rankings.length} de até 10 nomes`}
                  </span>
                </summary>
                <div className="legislature-ranking-group-body">
                  <CoverageSummary coverage={groupCoverage} />
                  <p className="legislature-ranking-explanation">
                    {group.rankingAmountStage === "destination"
                      ? "A base federal informa o valor destinado a Barreiras. Empenho e pagamento aparecem separadamente quando localizados."
                      : "A LOA da Bahia informa o valor autorizado para Barreiras. Autorização não significa que o valor foi empenhado, liquidado ou pago."}
                  </p>
                  {group.rankings.length === 0 ? (
                    <p className="legislature-ranking-empty">
                      Nenhuma autoria individual foi encontrada nos anos já
                      cobertos deste recorte. Isso não significa valor zero.
                    </p>
                  ) : (
                    <div className="legislature-ranking-list">
                      {group.rankings.map((row) => (
                        <LegislatureRankingRow
                          group={group}
                          key={`${row.authorKey}:${row.rankPosition}`}
                          row={row}
                        />
                      ))}
                    </div>
                  )}
                  <div className="legislature-ranking-methodology" role="note">
                    <p>{group.officialSourceNote}</p>
                    <p>
                      <strong>Por que 2023 não entra?</strong> As fontes atuais
                      informam o ano, mas não a data individual de cada emenda.
                      Como a legislatura mudou em fevereiro, atribuir todo o ano
                      a um único mandato produziria um resultado impreciso.
                    </p>
                    <p>
                      Este indicador mede somente recursos destinados a Barreiras
                      encontrados nas fontes; não mede sozinho todo o trabalho do
                      parlamentar nem comprova que o recurso foi executado.
                    </p>
                    <a href={group.officialSourceUrl} target="_blank" rel="noreferrer">
                      Fonte oficial da legislatura →
                    </a>
                    <a href="/recursos">Ver emendas, valores e documentos →</a>
                  </div>
                </div>
              </details>
            );
          })}
        </div>
      )}
    </section>
  );
}
