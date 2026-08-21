import type {
  BahiaSpecialTransferPayment,
  BahiaSpecialTransferRanking,
} from "../../lib/bahia-special-transfers.mjs";
import { formatBrlDecimal } from "../../lib/revenues";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  timeZone: "America/Bahia",
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(`${value}T12:00:00-03:00`));
}

function sumDecimalAmounts(values: readonly string[]): string {
  const hundred = BigInt(100);
  const cents = values.reduce((sum, value) => {
    const [units, fraction = ""] = value.split(".");
    return sum + BigInt(units) * hundred + BigInt(fraction.padEnd(2, "0"));
  }, BigInt(0));
  return `${cents / hundred}.${(cents % hundred).toString().padStart(2, "0")}`;
}

function federalLinkCopy(
  status: BahiaSpecialTransferPayment["federalLinkStatus"],
): string {
  if (status === "matched_cgu_unique") {
    return "O mesmo código de emenda também foi localizado uma única vez na base federal da CGU. Os valores das duas fontes não são somados.";
  }
  if (status === "conflict_non_unique_cgu") {
    return "O código apareceu mais de uma vez na base federal da CGU. O vínculo está sinalizado para auditoria e nenhum valor é somado.";
  }
  return "Este código não foi localizado no recorte federal preservado da CGU. Isso pode decorrer de diferenças de cobertura entre as fontes.";
}

function PaymentCard({ payment }: Readonly<{
  payment: BahiaSpecialTransferPayment;
}>) {
  return (
    <article className="transfer-card">
      <div className="transfer-card-heading">
        <div>
          <span className="transfer-card-kind">
            Emenda {payment.officialAmendmentCode}
          </span>
          <h3>{formatBrlDecimal(payment.paymentAmount)}</h3>
          <p>Pagamento registrado em {formatDate(payment.paymentDate)}</p>
        </div>
        <span className="transfer-status">Pago pelo Estado</span>
      </div>
      <p className="transfer-object">{payment.objectText}</p>
      <dl className="transfer-stage-grid">
        <div>
          <dt>Autor na fonte</dt>
          <dd>{payment.officialAuthorName}</dd>
          <span>
            {payment.associationStatus === "approved_official_author_code_crosswalk"
              ? "Identidade conferida por código oficial e período."
              : "Autoria ainda não ligada a um perfil institucional."}
          </span>
        </div>
        <div>
          <dt>Órgão pagador</dt>
          <dd>{payment.agencyName}</dd>
          <span>{payment.budgetUnitName}</span>
        </div>
        <div>
          <dt>Data e ordem</dt>
          <dd>{formatDate(payment.paymentDate)}</dd>
          <span>Ordem {payment.paymentNumber}</span>
        </div>
      </dl>
      <p className="transfer-caution">
        <strong>Limite desta evidência:</strong> o objeto do pagamento menciona
        Barreiras. Isso não comprova que a Prefeitura recebeu o dinheiro e não
        comprova que o bem, serviço ou obra foi entregue.
      </p>
      <details className="transfer-details">
        <summary>Trecho oficial e rastreabilidade</summary>
        <p>{payment.evidenceText}</p>
        <p>{federalLinkCopy(payment.federalLinkStatus)}</p>
        <dl>
          <div>
            <dt>Hash do arquivo</dt>
            <dd className="transfer-hash">{payment.sourceArtifactSha256}</dd>
          </div>
          <div>
            <dt>Hash da evidência</dt>
            <dd className="transfer-hash">{payment.evidenceSha256}</dd>
          </div>
        </dl>
        <a href={payment.paymentUrl} rel="noreferrer" target="_blank">
          Conferir o pagamento no portal oficial da Bahia ↗
        </a>
        {" · "}
        <a href={payment.sourceUrl} rel="noreferrer" target="_blank">
          Abrir a base oficial preservada ↗
        </a>
      </details>
    </article>
  );
}

export default function BahiaSpecialTransfersPanel({
  payments,
  ranking,
}: Readonly<{
  payments: readonly BahiaSpecialTransferPayment[] | null;
  ranking: readonly BahiaSpecialTransferRanking[] | null;
}>) {
  const paidTotal = sumDecimalAmounts(
    payments?.map((payment) => payment.paymentAmount) ?? [],
  );
  const panelState =
    payments === null || ranking === null
      ? "Processamento estadual ainda indisponível"
      : payments.length === 0
        ? "Fonte processada sem pagamentos territoriais localizados"
        : "Execução estadual encontrada";
  return (
    <section className="transfer-ranking" aria-labelledby="bahia-special-title">
      <div className="transfer-section-heading">
        <div>
          <span className="eyebrow">{panelState}</span>
          <h2 id="bahia-special-title">
            Pagamentos do Estado cujo objeto menciona Barreiras
          </h2>
        </div>
        <p>Fonte: dados abertos e Portal da Transparência do Estado da Bahia.</p>
      </div>
      <aside className="transfer-reading-guide">
        <strong>Leia este número sem confundir as etapas</strong>
        <p>
          Este conjunto mostra ordens marcadas como pagas pelo Estado da Bahia
          cujo texto oficial menciona Barreiras. Ele não comprova que a Prefeitura
          recebeu o dinheiro e não comprova que o bem, serviço ou obra foi entregue.
        </p>
        <p>
          O total abaixo pertence somente a esta base estadual: não é somado aos valores da LOA, da CGU ou do Transferegov. Coincidências são mostradas
          por código apenas para conferência, sem duplicar dinheiro.
        </p>
      </aside>
      {payments === null || ranking === null ? (
        <p className="transfer-empty">
          A projeção pública destes pagamentos ainda não está disponível. Isso é
          ausência de processamento, não prova de valor zero.
        </p>
      ) : payments.length === 0 ? (
        <p className="transfer-empty">
          Nenhum pagamento com menção literal a Barreiras foi encontrado no
          recorte processado desta fonte estadual.
        </p>
      ) : (
        <>
          <dl className="transfer-stage-grid">
            <div>
              <dt>Pago nesta fonte</dt>
              <dd>{formatBrlDecimal(paidTotal)}</dd>
              <span>{payments.length.toLocaleString("pt-BR")} ordem(ns) localizada(s)</span>
            </div>
            <div>
              <dt>Emendas distintas</dt>
              <dd>{new Set(payments.map((row) => row.officialAmendmentCode)).size}</dd>
              <span>Contagem por código oficial, sem repetir pagamentos.</span>
            </div>
            <div>
              <dt>O que está comprovado</dt>
              <dd>Pagamento estadual</dd>
              <span>Com menção literal a Barreiras no objeto.</span>
            </div>
          </dl>
          <details className="historical-proposal-year">
            <summary>
              Ranking desta fonte estadual
              <small>{ranking.length.toLocaleString("pt-BR")} autoria(s) reconciliada(s)</small>
            </summary>
            <div className="transfer-ranking-list">
              {ranking.map((row) => (
                <article className="transfer-ranking-card" key={row.authorKey}>
                  <span className="transfer-rank">{row.rankPosition}</span>
                  <div className="transfer-ranking-name">
                    <h3>{row.officialAuthorName}</h3>
                    <span>Autoria ligada por código oficial e período</span>
                  </div>
                  <dl>
                    <div><dt>Pago nesta fonte</dt><dd>{formatBrlDecimal(row.paidAmount)}</dd></div>
                    <div><dt>Emendas</dt><dd>{row.amendmentCount}</dd></div>
                    <div><dt>Ordens</dt><dd>{row.paymentCount}</dd></div>
                  </dl>
                  <div className="transfer-profile-context">
                    <p>
                      Período dos pagamentos: {formatDate(row.firstPaymentDate)} a {formatDate(row.lastPaymentDate)}.
                    </p>
                    <a className="transfer-profile-link" href={row.representativeProfileUrl} rel="noreferrer" target="_blank">
                      Conferir perfil institucional ↗
                    </a>
                  </div>
                </article>
              ))}
            </div>
          </details>
          <details className="historical-proposal-year">
            <summary>
              Conferir pagamentos e documentos
              <small>{payments.length.toLocaleString("pt-BR")} registro(s)</small>
            </summary>
            <div className="transfer-card-list">
              {payments.map((payment) => (
                <PaymentCard payment={payment} key={payment.paymentId} />
              ))}
            </div>
          </details>
        </>
      )}
    </section>
  );
}
