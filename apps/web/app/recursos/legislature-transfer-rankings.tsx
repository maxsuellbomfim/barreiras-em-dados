import { formatBrlDecimal } from "../../lib/revenues";
import type {
  CguLegislatureRankingGroup,
  CguLegislatureRankingRow,
} from "../../lib/cgu-federal-amendments.mjs";
import type {
  ParliamentaryLegislatureRankingGroup,
  ParliamentaryLegislatureRankingRow,
} from "../../lib/parliamentary-legislature-rankings.mjs";
import type { ParliamentaryLegislatureCoverageRow } from
  "../../lib/parliamentary-legislature-coverage.mjs";
import {
  describeParliamentaryYearCoverageStatus,
  type ParliamentaryLegislatureYearCoverageRow,
} from "../../lib/parliamentary-legislature-year-coverage.mjs";

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
            Perfil oficial relacionado à autoria →
          </a>
        ) : (
          <span>Perfil oficial ainda não associado à autoria</span>
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

function CguLegislatureRow({
  row,
}: Readonly<{ row: CguLegislatureRankingRow }>) {
  return (
    <article className="legislature-ranking-row">
      <span className="transfer-rank" aria-label={`${row.rankPosition}º lugar`}>
        {row.rankPosition}º
      </span>
      <div className="legislature-ranking-person">
        <h4>{row.authorName}</h4>
        <p>
          {row.amendmentCount.toLocaleString("pt-BR")} emenda(s) executada(s)
          {row.firstYear === row.lastYear
            ? ` em ${row.firstYear}`
            : ` entre ${row.firstYear} e ${row.lastYear}`}
        </p>
        <a
          className="legislature-ranking-detail-link"
          href="/recursos?origem=federal-execucao"
        >
          Ver cada emenda no arquivo da CGU →
        </a>
      </div>
      <dl className="legislature-ranking-values">
        <div>
          <dt>Empenhado no orçamento federal</dt>
          <dd>{formatBrlDecimal(row.committedAmount)}</dd>
        </div>
        <div>
          <dt>Pago efetivo (pago + restos pagos)</dt>
          <dd>{formatBrlDecimal(row.effectivePaidAmount)}</dd>
        </div>
      </dl>
    </article>
  );
}

function CguLegislatureBlock({
  group,
}: Readonly<{ group: CguLegislatureRankingGroup | null }>) {
  return (
    <div className="legislature-ranking-methodology" role="note">
      <p>
        <strong>Outra fonte, outro caminho do dinheiro: execução direta (CGU).</strong>{" "}
        O painel acima cobre convênios e transferências registrados no
        Transferegov. Emendas executadas diretamente no orçamento de órgãos
        federais não passam por lá — aparecem no arquivo aberto da CGU. As duas
        séries ficam separadas e nunca são somadas; um mesmo parlamentar pode
        aparecer só em uma delas sem que isso seja erro.
      </p>
      {group === null ? (
        <p>
          O arquivo da CGU não publicou linhas para Barreiras nos anos completos
          desta legislatura. Isso descreve a fonte, não prova ausência de
          emendas.
        </p>
      ) : (
        <>
          {group.people.length > 0 ? (
            <div className="legislature-ranking-list">
              {group.people.map((row) => (
                <CguLegislatureRow key={`cgu:person:${row.authorKey}`} row={row} />
              ))}
            </div>
          ) : null}
          {group.collectives.length > 0 ? (
            <>
              <p>
                Autoria coletiva (bancadas e comissões) — nunca atribuída a um
                parlamentar individual:
              </p>
              <div className="legislature-ranking-list">
                {group.collectives.map((row) => (
                  <CguLegislatureRow
                    key={`cgu:collective:${row.authorKey}`}
                    row={row}
                  />
                ))}
              </div>
            </>
          ) : null}
        </>
      )}
      <p>
        Exercícios fora dos anos completos desta legislatura (inclusive o ano de
        transição 2023) permanecem visíveis na aba Execução federal.
      </p>
      <a href="/recursos?origem=federal-execucao">
        Conferir a série completa da CGU, emenda por emenda →
      </a>
    </div>
  );
}

function CoverageSummary({
  coverage,
  years,
}: Readonly<{
  coverage: ParliamentaryLegislatureCoverageRow | null;
  years: readonly ParliamentaryLegislatureYearCoverageRow[] | null;
}>) {
  if (coverage === null) {
    return (
      <p className="legislature-coverage-unavailable">
        Diagnóstico de cobertura indisponível nesta consulta. O ranking não deve
        ser interpretado como acervo completo.
      </p>
    );
  }
  const observedYears = years?.filter((row) =>
    row.observationStatus === "observed"
  ).map((row) => row.fiscalYear) ?? [];
  const unresolvedYears = years?.filter((row) =>
    row.observationStatus !== "observed"
  ) ?? [];
  return (
    <div className="legislature-coverage" role="note">
      <strong>O que esta fonte permitiu conferir neste recorte</strong>
      <dl>
        <div>
          <dt>Anos com registros</dt>
          <dd>
            {years === null
              ? "diagnóstico indisponível"
              : observedYears.length === 0
                ? "nenhum ano observado"
                : observedYears.join(", ")}
          </dd>
        </div>
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
        {years === null
          ? "A cobertura por ano está temporariamente indisponível; este ranking não deve ser lido como acervo completo."
          : unresolvedYears.length > 0
            ? `Recorte parcial: ${unresolvedYears.map((row) =>
              `${row.fiscalYear} — ${describeParliamentaryYearCoverageStatus(row.observationStatus)}`
            ).join("; ")}. Nenhum desses estados significa valor zero.`
            : "Todos os anos previstos têm ao menos um registro individual no ranking. Isso ainda não prova que o universo oficial esteja completo."}
      </p>
    </div>
  );
}

export default function LegislatureTransferRankings({
  groups,
  coverage,
  yearCoverage,
  cguGroups,
}: Readonly<{
  groups: readonly ParliamentaryLegislatureRankingGroup[] | null;
  coverage: readonly ParliamentaryLegislatureCoverageRow[] | null;
  yearCoverage: readonly ParliamentaryLegislatureYearCoverageRow[] | null;
  cguGroups: readonly CguLegislatureRankingGroup[] | null;
}>) {
  return (
    <section
      id="emendas-por-legislatura"
      className="transfer-legislature-rankings"
      aria-labelledby="legislature-rankings-title"
    >
      <div className="section-heading">
        <span className="eyebrow">Comparação por mandato</span>
        <h2 id="legislature-rankings-title">
          Quem aparece com mais recursos no acervo de cada legislatura?
        </h2>
        <p>
          Compare parlamentares sem misturar esferas ou mandatos. A ordem usa o
          valor oficial destinado pela fonte federal ou autorizado na LOA da
          Bahia; empenho, liquidação e pagamento aparecem separados e nunca
          alteram a posição. Nas legislaturas federais, a execução direta do
          orçamento (arquivo da CGU) aparece como série própria, separada e
          nunca somada aos convênios.
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
            const matchedYearCoverage = yearCoverage?.filter((row) =>
              row.sphere === group.sphere &&
              row.legislatureNumber === group.legislatureNumber
            ) ?? null;
            const expectedYearCount =
              group.fullFiscalYearTo - group.fullFiscalYearFrom + 1;
            const groupYearCoverage = matchedYearCoverage?.length ===
              expectedYearCount
              ? matchedYearCoverage
              : null;
            const unresolvedYears = groupYearCoverage?.filter((row) =>
              row.observationStatus !== "observed"
            ) ?? [];
            const yearCoverageLabel = groupYearCoverage === null
              ? "cobertura anual indisponível"
              : unresolvedYears.length > 0
                ? `recorte parcial · ${unresolvedYears.length} ano(s) a conferir`
                : "todos os anos previstos têm registros";
            const foundAuthors = groupCoverage?.authorCount ??
              group.rankings.length;
            const rankingScopeLabel = group.rankings.length === 0
              ? "sem registros no recorte"
              : `${current ? "atual" : "encerrada"} · ${yearCoverageLabel} · top ${group.rankings.length} de ${foundAuthors} autor(es) encontrado(s)`;
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
                  <span>{rankingScopeLabel}</span>
                </summary>
                <div className="legislature-ranking-group-body">
                  <CoverageSummary
                    coverage={groupCoverage}
                    years={groupYearCoverage}
                  />
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
                  {group.sphere === "federal" ? (
                    <CguLegislatureBlock
                      group={cguGroups?.find((cgu) =>
                        cgu.legislatureNumber === group.legislatureNumber
                      ) ?? null}
                    />
                  ) : null}
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
                    <a
                      href={group.sphere === "state"
                        ? "/recursos?origem=estadual"
                        : "/recursos?origem=federal-historico"}
                    >
                      Explorar a fonte e os demais registros →
                    </a>
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
