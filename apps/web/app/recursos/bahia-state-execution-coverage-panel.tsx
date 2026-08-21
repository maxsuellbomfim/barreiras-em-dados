import type { BahiaStateExecutionCoverage } from
  "../../lib/bahia-state-execution-coverage.mjs";

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: "America/Bahia",
});

export default function BahiaStateExecutionCoveragePanel({
  rows,
}: Readonly<{
  rows: readonly BahiaStateExecutionCoverage[] | null;
}>) {
  const sourceUrl = rows?.[0]?.sourceUrl;
  return (
    <details className="transfer-methodology transfer-source-coverage">
      <summary>Cobertura do arquivo estadual de execução</summary>
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">Retrato estadual do FIPLAN</span>
          <h2>O que o arquivo da Bahia permite conferir</h2>
        </div>
        <p>
          Quantidade de linhas financeiras e de autores presentes em cada ano do
          arquivo oficial, sem somar valores.
        </p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Esta tabela não é um ranking municipal</strong>
        <p>
          O arquivo de execução estadual <strong>não informa o município</strong>
          {" "}nem o número individual da emenda. Por isso, estas contagens não
          são valores destinados a Barreiras e não podem ser usadas para atribuir
          pagamentos a um parlamentar na cidade.
        </p>
        <p>
          Elas comprovam que o retrato estadual foi preservado e processado. A
          atribuição territorial continua dependendo do anexo da LOA ou de outra
          evidência oficial que cite Barreiras.
        </p>
      </aside>
      {rows === null || rows.length === 0 ? (
        <p className="transfer-coverage-unavailable">
          A cobertura do arquivo estadual está temporariamente indisponível. Isso
          não significa ausência de execução financeira.
        </p>
      ) : (
        <div className="transfer-source-coverage-scroll">
          <table>
            <caption>Linhas observadas no retrato estadual do FIPLAN</caption>
            <thead>
              <tr>
                <th scope="col">Ano</th>
                <th scope="col">Linhas financeiras</th>
                <th scope="col">Autores distintos</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.fiscalYear}>
                  <th scope="row">{row.fiscalYear}</th>
                  <td>{row.sourceAggregateCount.toLocaleString("pt-BR")}</td>
                  <td>{row.sourceAuthorCount.toLocaleString("pt-BR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows?.[0] ? (
        <p className="transfer-coverage-caveat">
          Arquivo conferido em {dateTimeFormatter.format(new Date(rows[0].sourceCollectedAt))}
          {" · "}
          <a href={sourceUrl} rel="noreferrer" target="_blank">abrir fonte oficial</a>
          {" · hash "}<code>{rows[0].sourceArtifactSha256.slice(0, 12)}…</code>
        </p>
      ) : null}
    </details>
  );
}
