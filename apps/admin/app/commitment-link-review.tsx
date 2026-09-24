"use client";

import { useCallback, useEffect, useState } from "react";

type RpcResult = { data: unknown; error: { message: string } | null };
export type RpcCall = (fn: string, args: Record<string, unknown>) => PromiseLike<RpcResult>;

type Candidate = Readonly<{
  contract_raw_record_id: string;
  contract_portal_id: string;
  contract_number: string;
  contractor: string;
  contract_object: string | null;
  contract_value_text: string | null;
  document_url: string | null;
}>;

type Sample = Readonly<{
  commitment_key: string;
  commitment_number: string;
  issue_date: string;
  public_body: string;
  amount_text: string;
  cited_excerpt: string;
}>;

type ReviewGroup = Readonly<{
  group_key: string;
  reason: "favorecido_divergente" | "varios_contratos";
  creditor_name: string;
  pending_count: number;
  link_ids: readonly string[];
  candidates: readonly Candidate[] | null;
  samples: readonly Sample[] | null;
  first_issue_date: string | null;
  last_issue_date: string | null;
}>;

type ReviewState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "denied" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; groups: readonly ReviewGroup[] }>;

type Decision = "approved" | "rejected" | "changes_requested";

const REASON_LABELS: Readonly<Record<ReviewGroup["reason"], string>> = {
  favorecido_divergente: "favorecido diferente do contratado",
  varios_contratos: "número com mais de um contrato no portal",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

export function CommitmentLinkReview({ rpc }: Readonly<{ rpc: RpcCall }>) {
  const [state, setState] = useState<ReviewState>({ kind: "loading" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    const { data, error } = await rpc("get_commitment_link_review_groups", {
      page_size: 50,
    });
    if (error) {
      setState(
        error.message.includes("revisores ativos")
          ? { kind: "denied" }
          : { kind: "error", message: error.message },
      );
      return;
    }
    setState({ kind: "ready", groups: (data ?? []) as ReviewGroup[] });
  }, [rpc]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = useCallback(
    async (
      group: ReviewGroup,
      decision: Decision,
      contractRawRecordId: string | null,
      note: string,
    ): Promise<string | null> => {
      setBusy(true);
      try {
        const { error } = await rpc("review_commitment_link_group", {
          p_link_ids: group.link_ids,
          p_review_decision: decision,
          p_contract_raw_record_id: decision === "approved" ? contractRawRecordId : null,
          p_review_note: note,
        });
        if (error) return `A revisão não foi registrada: ${error.message}`;
        await load();
        return null;
      } finally {
        setBusy(false);
      }
    },
    [load, rpc],
  );

  if (state.kind === "loading") {
    return <p aria-live="polite">Carregando citações de contrato para revisão…</p>;
  }
  if (state.kind === "denied") {
    return (
      <p className="status-error" role="alert">
        Sua conta não está cadastrada como revisora ativa. A fila de ligações
        permanece restrita.
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="status-error" role="alert">
        A fila de ligações não pôde ser carregada: {state.message}
      </p>
    );
  }
  if (state.groups.length === 0) {
    return (
      <div className="empty-state">
        Nenhuma citação de contrato aguardando revisão. Empenhos sem citação ou
        com contrato ausente do portal não entram nesta fila.
      </div>
    );
  }
  const pending = state.groups.reduce((total, group) => total + group.pending_count, 0);
  return (
    <section aria-labelledby="commitment-link-review-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Rastro do dinheiro</span>
        <h2 id="commitment-link-review-title">Empenhos que citam contrato</h2>
        <p>
          O histórico do empenho cita um contrato, mas a regra não confirmou a
          ligação. Confirme só quando o favorecido e o contratado forem a mesma
          pessoa jurídica (grafia diferente, nome abreviado); rejeite quando
          forem empresas distintas. Cada decisão vale para o grupo inteiro,
          fica registrada por empenho e pode ser retirada depois.
        </p>
        <p className="meta">
          {state.groups.length} grupo(s) carregado(s) com{" "}
          {pending.toLocaleString("pt-BR")} empenho(s), dos maiores para os
          menores.
        </p>
      </div>
      {state.groups.map((group) => (
        <ReviewGroupCard key={group.group_key} group={group} busy={busy} onDecide={decide} />
      ))}
    </section>
  );
}

function ReviewGroupCard({
  group,
  busy,
  onDecide,
}: Readonly<{
  group: ReviewGroup;
  busy: boolean;
  onDecide: (
    group: ReviewGroup,
    decision: Decision,
    contractRawRecordId: string | null,
    note: string,
  ) => Promise<string | null>;
}>) {
  const candidates = group.candidates ?? [];
  const [selected, setSelected] = useState<string | null>(
    candidates.length === 1 ? candidates[0].contract_raw_record_id : null,
  );
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const noteReady = note.trim().length >= 5;

  async function decide(decision: Decision) {
    setError(null);
    const failure = await onDecide(group, decision, selected, note);
    if (failure) setError(failure);
  }

  return (
    <article aria-label="Grupo de empenhos que citam contrato">
      <div className="card-top">
        <h3>{group.creditor_name}</h3>
        <span className="badge badge-type">
          {group.pending_count.toLocaleString("pt-BR")} empenho(s) ·{" "}
          {REASON_LABELS[group.reason]}
        </span>
      </div>
      <p className="meta">
        Empenhos de {formatDate(group.first_issue_date)} a{" "}
        {formatDate(group.last_issue_date)}.
      </p>
      <fieldset>
        <legend>Contrato citado no portal</legend>
        {candidates.map((candidate) => (
          <label key={candidate.contract_raw_record_id} className="candidate-option">
            <input
              type="radio"
              name={`contract-${group.group_key}`}
              value={candidate.contract_raw_record_id}
              checked={selected === candidate.contract_raw_record_id}
              onChange={() => setSelected(candidate.contract_raw_record_id)}
            />{" "}
            Contrato {candidate.contract_number} (id {candidate.contract_portal_id}) ·
            contratado: <strong>{candidate.contractor}</strong>
            {candidate.contract_value_text ? ` · ${candidate.contract_value_text}` : ""}
            {candidate.contract_object ? (
              <span className="meta"> · {candidate.contract_object}</span>
            ) : null}
            {candidate.document_url ? (
              <>
                {" "}
                <a href={candidate.document_url} target="_blank" rel="noreferrer">
                  abrir contrato
                </a>
              </>
            ) : null}
          </label>
        ))}
      </fieldset>
      <details>
        <summary>Exemplos de empenhos do grupo</summary>
        <ul>
          {(group.samples ?? []).map((sample) => (
            <li key={sample.commitment_key}>
              Empenho {sample.commitment_number} · {sample.issue_date} ·{" "}
              {sample.public_body} · valor {sample.amount_text} — “
              {sample.cited_excerpt}”
            </li>
          ))}
        </ul>
      </details>
      <label htmlFor={`link-note-${group.group_key}`}>Justificativa da revisão</label>
      <textarea
        id={`link-note-${group.group_key}`}
        rows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Ex.: mesmo CNPJ no contrato e na nota; nome do contratado abreviado no cadastro."
      />
      {error ? (
        <p className="status-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="actions-row">
        <button
          type="button"
          disabled={busy || !noteReady || selected === null}
          onClick={() => void decide("approved")}
        >
          Mesma empresa: confirmar ligação
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || !noteReady}
          onClick={() => void decide("changes_requested")}
        >
          Pedir evidência
        </button>
        <button
          type="button"
          className="destructive"
          disabled={busy || !noteReady}
          onClick={() => void decide("rejected")}
        >
          Empresa diferente: rejeitar
        </button>
      </div>
      <p className="meta">
        Confirmar publica os {group.pending_count.toLocaleString("pt-BR")}{" "}
        empenho(s) no contrato escolhido com o rótulo &quot;confirmada por revisão
        humana&quot;. Rejeitar ou pedir evidência não publica nada.
      </p>
    </article>
  );
}
