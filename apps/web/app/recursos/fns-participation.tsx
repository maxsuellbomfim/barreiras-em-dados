import type { FnsReviewedLink } from "../../lib/fns-reviewed-links.mjs";

export function FnsParticipation({ link }: Readonly<{ link?: FnsReviewedLink }>) {
  if (!link) return null;
  return (
    <aside className="transfer-reading-guide fns-participation" aria-label="Participação informada pelo Fundo Nacional de Saúde">
      <dl>
        <dt>Solicitante informado pelo FNS</dt>
        <dd><strong>{link.requesterName}</strong></dd>
      </dl>
      <p>
        O Fundo Nacional de Saúde cita esse nome como solicitante deste pagamento.
        A autoria da emenda continua sendo da Comissão da Saúde.
        Esta informação não acrescenta valor ao total nem ao ranking.
      </p>
      <a className="transfer-source-link" href={link.sourceUrl} rel="noreferrer" target="_blank">
        Consultar a fonte oficial do FNS →
      </a>
      <details className="transfer-details">
        <summary>Como conferir esta informação</summary>
        <p>
          O pagamento e sua ordem bancária no FNS foram conferidos com o documento{" "}
          <code>{link.documentCode}</code> da CGU. Esta informação não comprova,
          por si só, que uma obra ou serviço foi executado.
        </p>
        <p>
          Revisão registrada em{" "}
          {new Intl.DateTimeFormat("pt-BR", { timeZone: "America/Sao_Paulo" }).format(new Date(link.reviewedAt))}.
        </p>
        <p>Hash do pagamento FNS: <code>{link.paymentSha256}</code></p>
        <p>Hash da ordem bancária FNS: <code>{link.orderSha256}</code></p>
      </details>
    </aside>
  );
}
