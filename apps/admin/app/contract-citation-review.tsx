"use client";

import { useCallback, useEffect, useState } from "react";

import type { RpcCall } from "./commitment-link-review";

type SampleRow = Readonly<{
  sample_order: number;
  sample_reason: string;
  category: "sem_correspondencia" | "publicado_no_pncp";
  public_body: string;
  creditor_name: string;
  creditor_is_entity: boolean;
  cited_number: string;
  cited_excerpt: string;
  commitments: number;
  paid_amount: string;
  first_issue_date: string;
  last_issue_date: string;
  latest_commitment_key: string;
  list_read_on: string;
  pncp_url: string | null;
  portal_contracts_url: string;
  current_decision: string | null;
  current_reviewed_at: string | null;
  methodology_version: string;
}>;

type SampleState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "denied" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; rows: readonly SampleRow[] }>;

type Decision = "approved" | "changes_requested" | "rejected" | "withdrawn";

const DECISION_LABELS: Readonly<Record<string, string>> = {
  approved: "aprovada — página pública exibe os dados",
  changes_requested: "ajustes pedidos — página segue sem dados",
  rejected: "rejeitada — página segue sem dados",
  withdrawn: "retirada — página voltou a ficar sem dados",
};

export function ContractCitationReview({ rpc }: Readonly<{ rpc: RpcCall }>) {
  const [state, setState] = useState<SampleState>({ kind: "loading" });
  const [checked, setChecked] = useState<ReadonlySet<number>>(new Set());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    const { data, error: rpcError } = await rpc("get_contract_citation_review_sample", {});
    if (rpcError) {
      setState(
        rpcError.message.includes("revisores ativos")
          ? { kind: "denied" }
          : { kind: "error", message: rpcError.message },
      );
      return;
    }
    setState({ kind: "ready", rows: (data ?? []) as SampleRow[] });
  }, [rpc]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(decision: Decision) {
    setBusy(true);
    setError(null);
    try {
      const { error: rpcError } = await rpc("review_contract_citation_comparison", {
        p_decision: decision,
        p_rationale: note,
        p_checked_groups: checked.size,
      });
      if (rpcError) {
        setError(`A conferência não foi registrada: ${rpcError.message}`);
        return;
      }
      setNote("");
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return <p aria-live="polite">Carregando a amostra de citações de contrato…</p>;
  }
  if (state.kind === "denied") return null;
  if (state.kind === "error") {
    return (
      <p className="status-error" role="alert">
        A amostra de citações de contrato não pôde ser carregada: {state.message}
      </p>
    );
  }
  const current = state.rows[0];
  const noteReady = note.trim().length >= 5;
  return (
    <section aria-labelledby="contract-citation-review-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Publicação condicionada (ADR 0096)</span>
        <h2 id="contract-citation-review-title">
          Contratos citados sem correspondência na lista do portal
        </h2>
        <p>
          Para cada caso, procure o número na{" "}
          <a href={current?.portal_contracts_url} target="_blank" rel="noreferrer">
            lista de contratos do portal
          </a>{" "}
          (e no PNCP quando houver link). Marque os casos que você conferiu. Aprove só se a
          ausência se confirmar na maior parte deles; se o contrato aparecer com outro número ou
          sufixo, peça ajustes e descreva o padrão. A decisão vale para a versão{" "}
          {current?.methodology_version}.
        </p>
        <p className="meta">
          Situação atual:{" "}
          {current?.current_decision
            ? `${DECISION_LABELS[current.current_decision] ?? current.current_decision} em ${new Date(
                current.current_reviewed_at ?? "",
              ).toLocaleString("pt-BR")}`
            : "nenhuma conferência registrada — página pública sem dados"}
        </p>
      </div>
      <ol>
        {state.rows.map((row) => (
          <li key={row.sample_order}>
            <label className="candidate-option">
              <input
                type="checkbox"
                checked={checked.has(row.sample_order)}
                onChange={() =>
                  setChecked((previous) => {
                    const next = new Set(previous);
                    if (next.has(row.sample_order)) next.delete(row.sample_order);
                    else next.add(row.sample_order);
                    return next;
                  })
                }
              />{" "}
              <strong>{row.cited_number}</strong> · {row.creditor_name}
              {row.creditor_is_entity ? "" : " (pessoa física: não será nomeada)"} ·{" "}
              {row.public_body}
              <span className="meta">
                {" "}
                · {row.commitments} empenho(s), pago {row.paid_amount}, último{" "}
                {row.latest_commitment_key} · “{row.cited_excerpt}” · {row.sample_reason}
                {row.category === "publicado_no_pncp" ? " · mesmo número no PNCP" : ""}
              </span>
              {row.pncp_url ? (
                <>
                  {" "}
                  <a href={row.pncp_url} target="_blank" rel="noreferrer">
                    PNCP
                  </a>
                </>
              ) : null}
            </label>
          </li>
        ))}
      </ol>
      <label htmlFor="contract-citation-note">Justificativa da conferência</label>
      <textarea
        id="contract-citation-note"
        rows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Ex.: conferi 22 casos; 20 ausentes da lista, 2 publicados com sufixo -FMS."
      />
      {error ? (
        <p className="status-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="actions-row">
        <button
          type="button"
          disabled={busy || !noteReady || checked.size === 0}
          onClick={() => void decide("approved")}
        >
          Aprovar publicação ({checked.size} conferido(s))
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || !noteReady}
          onClick={() => void decide("changes_requested")}
        >
          Pedir ajustes na regra
        </button>
        <button
          type="button"
          className="destructive"
          disabled={busy || !noteReady}
          onClick={() => void decide(current?.current_decision === "approved" ? "withdrawn" : "rejected")}
        >
          {current?.current_decision === "approved" ? "Retirar publicação" : "Rejeitar"}
        </button>
      </div>
    </section>
  );
}
