import {
  formatSanctionCnpj,
  sanctionRegistryLabel,
  type SupplierSanction,
} from "../../lib/supplier-sanctions";

export function SupplierSanctionCard({
  sanction,
}: Readonly<{ sanction: SupplierSanction }>) {
  return (
    <article className="digest-card">
      <div className="track-top">
        <span>{sanctionRegistryLabel(sanction.registry)}</span>
        <span className="track-status">
          {sanction.endDateText
            ? `vigência até ${sanction.endDateText}`
            : "fim de vigência não informado"}
        </span>
      </div>
      <h3 className="procurement-object">{sanction.sanctionedName}</h3>
      <dl className="procurement-values">
        <div>
          <dt>CNPJ no cadastro</dt>
          <dd>{formatSanctionCnpj(sanction.supplierCnpj)}</dd>
        </div>
        <div>
          <dt>Tipo de sanção</dt>
          <dd>{sanction.sanctionType ?? "não informado pela fonte"}</dd>
        </div>
        <div>
          <dt>Órgão sancionador</dt>
          <dd>
            {sanction.sanctioningBody ?? "não informado"}
            {sanction.sanctioningBodyUf ? ` (${sanction.sanctioningBodyUf})` : ""}
          </dd>
        </div>
        <div>
          <dt>Início informado</dt>
          <dd>{sanction.startDateText ?? "não informado"}</dd>
        </div>
        {sanction.processNumber ? (
          <div>
            <dt>Processo</dt>
            <dd>{sanction.processNumber}</dd>
          </div>
        ) : null}
      </dl>
      <p className="act-review-mode">
        Registro espelhado do cadastro federal na data da consulta. Uma sanção
        pode estar em discussão administrativa ou judicial; este painel não
        afirma culpa nem irregularidade em contratos específicos.
      </p>
      <p className="act-evidence">
        Consulta oficial preservada · hash {sanction.artifactSha256.slice(0, 12)}… ·{" "}
        <a
          href={`https://portaldatransparencia.gov.br/sancoes/consulta?cadastro=1&cpfCnpj=${sanction.supplierCnpj}`}
          target="_blank"
          rel="noreferrer"
        >
          Conferir no Portal da Transparência →
        </a>
      </p>
    </article>
  );
}
