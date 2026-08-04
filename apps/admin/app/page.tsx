"use client";

import { createClient, type Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useMemo, useState } from "react";

type FieldEntry = Readonly<{
  value: string | null;
  status: string;
  rule_id: string;
}>;

type QueueItem = Readonly<{
  result_id: string;
  candidate_type: string;
  extractor_version: string;
  validation_status: string;
  result_created_at: string;
  result_payload: {
    excerpt?: string;
    act_type?: string;
    fields?: Record<string, FieldEntry | string>;
  };
  assisted_payload?: {
    provider?: string;
    model?: string;
    summary?: string | null;
    clean_text?: string | null;
    suggestions?: Record<string, string | null>;
  } | null;
  artifact_sha256: string;
  artifact_source_url?: string | null;
  queue_reason?:
    | "missing_source_excerpt"
    | "ai_assistance_pending"
    | "needs_human_verification"
    | string;
  methodology_version: string;
}>;

type QueueState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "denied" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly QueueItem[] }>;

type HistoryItem = Readonly<{
  result_id: string;
  candidate_type: string;
  result_payload: QueueItem["result_payload"];
  artifact_sha256: string;
  decision: "approved" | "rejected";
  rationale: string;
  decided_at: string;
  methodology_version: string;
}>;

type HistoryState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly HistoryItem[] }>;

type TypeFilter = "todos" | "nomeacao" | "exoneracao";
type DecisionFilter = "todas" | "approved" | "rejected";
type AdminView = "fila" | "historico" | "financas" | "aliases";

type FinanceInventoryItem = Readonly<{
  document_id: string;
  resource: string;
  document_title: string;
  document_url: string;
  retrieved_at: string;
  artifact_sha256: string;
  byte_size: number;
  source_record_key: string | null;
  extraction_status: "published" | "failed" | "queued" | "preserved_only";
  latest_job_status: string | null;
  latest_error_code: string | null;
  latest_error_detail: string | null;
  published_rows: number;
  methodology_version: string;
}>;

type FinanceInventoryState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly FinanceInventoryItem[] }>;

type AdminMonthlyClosure = Readonly<{
  closure_id: string;
  fiscal_year: number;
  period_start: string;
  period_end: string;
  public_body_name: string;
  revenue_report_amount: string | null;
  expense_paid_amount: string | null;
  expense_committed_amount: string | null;
  expense_liquidated_amount: string | null;
  operational_difference_amount: string | null;
  closure_status: "operational" | "needs_data" | "needs_review";
  coverage_note: string;
}>;

type FinanceClosureState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly AdminMonthlyClosure[] }>;

type AliasCandidate = Readonly<{
  representative_external_id: string;
  candidate_id: string;
  canonical_name: string;
  party: string | null;
}>;

type AliasSuggestion = Readonly<{
  id: string;
  observed_name: string;
  source_record_keys: readonly string[];
  item_count: number;
  candidates: readonly AliasCandidate[];
  decision: "match" | "ambiguous" | "no_match";
  candidate_external_id: string | null;
  alias_kind: string;
  confidence: number;
  rationale: string;
  evidence: readonly string[];
  provider: string;
  model: string;
  prompt_version: string;
  status: "pending" | "accepted" | "rejected" | "needs_more_evidence";
  created_at: string;
}>;

type AliasState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "denied" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{ kind: "ready"; items: readonly AliasSuggestion[] }>;

const FIELD_LABELS: Readonly<Record<string, string>> = {
  person_name: "Pessoa",
  position: "Cargo",
  position_symbol: "Símbolo",
  organization: "Órgão",
  act_number: "Portaria nº",
  act_date: "Data do ato",
};

const PUBLIC_ACTS_URL = "https://barreiras-em-dados.vercel.app/atos";

function candidateLabel(type: string): string {
  if (type === "nomeacao") return "Nomeação";
  if (type === "exoneracao") return "Exoneração";
  return type;
}

function normalize(value: string): string {
  return value
    .toLocaleLowerCase("pt-BR")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function payloadSearchText(
  candidateType: string,
  payload: QueueItem["result_payload"],
): string {
  const fields = payload.fields ?? {};
  const values = Object.values(fields)
    .map((entry) =>
      typeof entry === "object" && entry !== null ? entry.value ?? "" : "",
    )
    .join(" ");
  return normalize(
    `${candidateLabel(candidateType)} ${values} ${payload.excerpt ?? ""}`,
  );
}

function financeResourceLabel(resource: string): string {
  const labels: Readonly<Record<string, string>> = {
    "pdc-receita-tributaria": "Receita tributária",
    "pdc-recursos-extraordinarios": "Recursos extraordinários",
    "pdc-resumo-execucao-da-receita": "Execução da receita",
    "pdc-resumo-execucao-da-despesa": "Execução da despesa",
    "pdc-transferencia": "Transferências",
    "pdc-emendas-parlamentares-receitas": "Emendas e receitas",
    rreo: "RREO",
    rgf: "RGF",
  };
  return labels[resource] ?? resource;
}

function financeStatusLabel(status: FinanceInventoryItem["extraction_status"]): string {
  if (status === "published") return "Publicado";
  if (status === "failed") return "Falhou — revisar";
  if (status === "queued") return "Na fila";
  return "Preservado — ainda não processado";
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 1024 * 1024) return `${Math.round(value / 1024).toLocaleString("pt-BR")} KB`;
  return `${(value / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

function formatDecimalAmount(value: string | null): string {
  if (value === null || !/^-?\d+(?:\.\d{1,2})?$/.test(value)) return "—";
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return "R$ " + (negative ? "-" : "") + grouped + "," + fraction.padEnd(2, "0");
}

function formatClosureMonth(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Bahia",
  }).format(new Date(value + "T12:00:00-03:00"));
}

function closureStatusLabel(status: AdminMonthlyClosure["closure_status"]): string {
  if (status === "operational") return "Fechamento operacional";
  if (status === "needs_review") return "Requer revisão";
  return "Faltam dados";
}

function FinanceClosureSummary({
  state,
}: Readonly<{ state: FinanceClosureState }>) {
  return (
    <section className="finance-closure-summary" aria-labelledby="finance-closure-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Fechamento mensal determinístico</span>
        <h2 id="finance-closure-title">Receita, pagamentos e cobertura</h2>
        <p>
          Valores retornados pelo fechamento oficial. O painel não recalcula
          totais e não trata a diferença como superávit fiscal.
        </p>
      </div>
      {state.kind === "loading" ? <p aria-live="polite">Carregando fechamentos…</p> : null}
      {state.kind === "error" ? (
        <p className="status-error" role="alert">
          Os fechamentos não puderam ser carregados: {state.message}
        </p>
      ) : null}
      {state.kind === "ready" ? (
        state.items.length === 0 ? (
          <div className="empty-state">Nenhum fechamento mensal disponível.</div>
        ) : (
          <div className="finance-closure-list">
            {state.items.slice(0, 12).map((closure) => (
              <article className="finance-closure-card" key={closure.closure_id}>
                <div className="card-top">
                  <h3>{formatClosureMonth(closure.period_start)}</h3>
                  <span className={"badge finance-closure-" + closure.closure_status}>
                    {closureStatusLabel(closure.closure_status)}
                  </span>
                </div>
                <p className="meta">{closure.public_body_name}</p>
                <dl>
                  <div>
                    <dt>Receita declarada</dt>
                    <dd>{formatDecimalAmount(closure.revenue_report_amount)}</dd>
                  </div>
                  <div>
                    <dt>Pagamentos</dt>
                    <dd>{formatDecimalAmount(closure.expense_paid_amount)}</dd>
                  </div>
                  <div>
                    <dt>Diferença operacional</dt>
                    <dd>{formatDecimalAmount(closure.operational_difference_amount)}</dd>
                  </div>
                </dl>
                <details>
                  <summary>Como interpretar este mês</summary>
                  <p>{closure.coverage_note}</p>
                </details>
              </article>
            ))}
          </div>
        )
      ) : null}
    </section>
  );
}

function FinanceInventory({
  state,
  closureState,
  search,
  onSearchChange,
  onReload,
}: Readonly<{
  state: FinanceInventoryState;
  closureState: FinanceClosureState;
  search: string;
  onSearchChange: (value: string) => void;
  onReload: () => void;
}>) {
  const items = state.kind === "ready" ? state.items : [];
  const normalizedSearch = normalize(search.trim());
  const visible = items.filter((item) => {
    if (!normalizedSearch) return true;
    return normalize(
      `${financeResourceLabel(item.resource)} ${item.document_title} ${item.document_url} ${item.latest_error_detail ?? ""}`,
    ).includes(normalizedSearch);
  });
  const counts = items.reduce(
    (summary, item) => ({ ...summary, [item.extraction_status]: summary[item.extraction_status] + 1 }),
    { published: 0, failed: 0, queued: 0, preserved_only: 0 },
  );

  return (
    <>
      <FinanceClosureSummary state={closureState} />
      <section aria-labelledby="finance-inventory-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Mapa do pipeline</span>
        <h2 id="finance-inventory-title">Documentos financeiros</h2>
        <p>
          Inventário dos PDFs preservados no portal municipal. “Preservado” significa que a cópia existe, mas ainda não virou dado normalizado.
        </p>
      </div>
      {state.kind === "loading" ? <p aria-live="polite">Carregando inventário…</p> : null}
      {state.kind === "error" ? <p className="status-error" role="alert">O inventário não pôde ser carregado: {state.message}</p> : null}
      {state.kind === "ready" ? (
        <>
          <dl className="finance-inventory-stats" aria-label="Resumo do inventário financeiro">
            <div><dt>Preservados</dt><dd>{items.length.toLocaleString("pt-BR")}</dd></div>
            <div><dt>Publicados</dt><dd>{counts.published.toLocaleString("pt-BR")}</dd></div>
            <div><dt>Falhas</dt><dd>{counts.failed.toLocaleString("pt-BR")}</dd></div>
            <div><dt>A processar</dt><dd>{(counts.preserved_only + counts.queued).toLocaleString("pt-BR")}</dd></div>
          </dl>
          <div className="toolbar">
            <input
              type="search"
              aria-label="Buscar documento financeiro"
              placeholder="Buscar por tipo, arquivo ou erro…"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
            />
            <button type="button" className="secondary" onClick={onReload}>Atualizar inventário</button>
          </div>
          <p className="result-count">Exibindo {visible.length.toLocaleString("pt-BR")} de {items.length.toLocaleString("pt-BR")} documentos</p>
          {visible.length === 0 ? <div className="empty-state">Nenhum documento corresponde à busca.</div> : null}
          {visible.map((item) => (
            <article aria-label="Documento financeiro preservado" key={item.document_id}>
              <div className="card-top">
                <h3>{financeResourceLabel(item.resource)}</h3>
                <span className={`badge finance-status-${item.extraction_status}`}>{financeStatusLabel(item.extraction_status)}</span>
              </div>
              <p className="finance-inventory-title">{item.document_title}</p>
              <dl>
                <div><dt>Coletado em</dt><dd>{new Date(item.retrieved_at).toLocaleString("pt-BR")}</dd></div>
                <div><dt>Tamanho</dt><dd>{formatBytes(item.byte_size)}</dd></div>
                <div><dt>Linhas publicadas</dt><dd>{item.published_rows.toLocaleString("pt-BR")}</dd></div>
                <div><dt>Parser</dt><dd>{item.methodology_version}</dd></div>
              </dl>
              {item.latest_error_detail ? <p className="finance-inventory-error"><strong>{item.latest_error_code ?? "Falha"}:</strong> {item.latest_error_detail}</p> : null}
              <p className="meta">
                <a href={item.document_url} target="_blank" rel="noreferrer">Abrir PDF oficial</a> · hash {item.artifact_sha256.slice(0, 12)}…
              </p>
            </article>
          ))}
        </>
      ) : null}
      </section>
    </>
  );
}

function AliasReview({
  state,
  onReview,
  busy,
}: Readonly<{
  state: AliasState;
  onReview: (
    item: AliasSuggestion,
    decision: "accepted" | "rejected" | "needs_more_evidence",
    note: string,
  ) => Promise<string | null>;
  busy: boolean;
}>) {
  if (state.kind === "loading") {
    return <p aria-live="polite">Carregando sugestões de aliases…</p>;
  }
  if (state.kind === "denied") {
    return (
      <p className="status-error" role="alert">
        Sua conta não está cadastrada como revisora ativa. A fila de aliases
        permanece restrita.
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="status-error" role="alert">
        A fila de aliases não pôde ser carregada: {state.message}
      </p>
    );
  }
  if (state.items.length === 0) {
    return (
      <div className="empty-state">
        Nenhuma sugestão de alias pendente. A IA só cria hipóteses; nomes ainda
        não revisados continuam separados no acervo público.
      </div>
    );
  }
  return (
    <section aria-labelledby="alias-review-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Identidade com cautela</span>
        <h2 id="alias-review-title">Aliases sugeridos pela IA</h2>
        <p>
          A sugestão não é prova e não publica nada. Aceite somente quando a
          fonte oficial e a evidência permitirem identificar a pessoa sem
          confundir homônimos.
        </p>
      </div>
      {state.items.map((item) => (
        <AliasSuggestionCard key={item.id} item={item} onReview={onReview} busy={busy} />
      ))}
    </section>
  );
}

function AliasSuggestionCard({
  item,
  onReview,
  busy,
}: Readonly<{
  item: AliasSuggestion;
  onReview: (
    item: AliasSuggestion,
    decision: "accepted" | "rejected" | "needs_more_evidence",
    note: string,
  ) => Promise<string | null>;
  busy: boolean;
}>) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const selected = item.candidates.find(
    (candidate) => candidate.representative_external_id === item.candidate_external_id,
  );

  async function decide(
    decision: "accepted" | "rejected" | "needs_more_evidence",
  ) {
    setError(null);
    const failure = await onReview(item, decision, note);
    if (failure) setError(failure);
  }

  return (
    <article aria-label="Sugestão de alias de representante">
      <div className="card-top">
        <h3>{item.observed_name}</h3>
        <span className="badge badge-type">
          {Math.round(item.confidence * 100)}% · {item.decision}
        </span>
      </div>
      <p>
        Aparece em <strong>{item.item_count.toLocaleString("pt-BR")}</strong>{" "}
        registro(s) da Câmara. A IA respondeu com {item.provider}/{item.model}.
      </p>
      <dl>
        <div>
          <dt>Hipótese principal</dt>
          <dd>
            {selected
              ? `${selected.canonical_name}${selected.party ? ` · ${selected.party}` : ""}`
              : "nenhuma"}
          </dd>
        </div>
        <div>
          <dt>Justificativa da IA</dt>
          <dd>{item.rationale}</dd>
        </div>
      </dl>
      {item.evidence.length > 0 ? (
        <details>
          <summary>Evidências e candidatos permitidos</summary>
          <ul>
            {item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
          </ul>
          <p className="meta">
            {item.candidates.map((candidate) => candidate.canonical_name).join(" · ")}
          </p>
        </details>
      ) : null}
      <label htmlFor={`alias-note-${item.id}`}>
        Justificativa da revisão
      </label>
      <textarea
        id={`alias-note-${item.id}`}
        rows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Ex.: confirmei o nome de urna no perfil oficial do TSE."
      />
      {error ? <p className="status-error" role="alert">{error}</p> : null}
      <div className="actions-row">
        <button
          type="button"
          disabled={busy || item.decision !== "match" || !selected}
          onClick={() => void decide("accepted")}
        >
          Aceitar alias
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || note.trim().length < 5}
          onClick={() => void decide("needs_more_evidence")}
        >
          Pedir evidência
        </button>
        <button
          type="button"
          className="destructive"
          disabled={busy || note.trim().length < 5}
          onClick={() => void decide("rejected")}
        >
          Rejeitar
        </button>
      </div>
      <p className="meta">
        Nada é alterado na autoria original. A aceitação grava apenas um alias
        revisado e auditável; a fonte continua sendo exibida como publicada.
      </p>
    </article>
  );
}

function ReviewCard({
  item,
  onDecide,
  busy,
}: {
  item: QueueItem;
  onDecide: (
    item: QueueItem,
    decision: "approved" | "rejected",
    rationale: string,
  ) => Promise<string | null>;
  busy: boolean;
}) {
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approved" | "rejected") {
    setError(null);
    const failure = await onDecide(item, decision, rationale);
    if (failure) {
      setError(failure);
    }
  }

  return (
    <article aria-label="Candidato de ato">
      <div className="card-top">
        <h2>{candidateLabel(item.candidate_type)}</h2>
        <span className="badge badge-type">
          {new Date(item.result_created_at).toLocaleDateString("pt-BR")}
        </span>
      </div>
      {item.assisted_payload?.clean_text ? (
        <div className="act-reading" aria-label="Ato reescrito para leitura">
          <p className="act-reading-head">
            O que está escrito no ato
            <span>
              recomposto por IA ({item.assisted_payload.provider}) a partir do
              texto oficial — confira no original antes de decidir
            </span>
          </p>
          <p className="act-reading-body">
            {item.assisted_payload.clean_text}
          </p>
        </div>
      ) : (
        <div className="act-reading act-reading-pending" role="status">
          <p className="act-reading-head">
            Leitura assistida indisponível
            <span>
              A IA ainda não recompôs este ato. O texto abaixo é o extraído do
              PDF e pode vir fragmentado.
            </span>
          </p>
        </div>
      )}
      {item.assisted_payload?.summary ? (
        <p className="assisted-summary">
          <strong>Em palavras simples:</strong>{" "}
          {item.assisted_payload.summary}
        </p>
      ) : null}
      <FieldList payload={item.result_payload} />
      {item.assisted_payload?.suggestions ? (
        <details className="assisted">
          <summary>Sugestões de campo pela IA (confira antes de usar)</summary>
          <dl>
            {Object.entries(FIELD_LABELS).map(([key, label]) => {
              const value = item.assisted_payload?.suggestions?.[key];
              if (!value) {
                return null;
              }
              return (
                <div key={key} style={{ display: "contents" }}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              );
            })}
          </dl>
        </details>
      ) : null}
      <details>
        <summary>Texto original extraído do PDF (pode vir fragmentado)</summary>
        <pre>{item.result_payload.excerpt ?? "sem trecho"}</pre>
      </details>
      <label htmlFor={`rationale-${item.result_id}`}>
        Justificativa da decisão (obrigatória)
      </label>
      <textarea
        id={`rationale-${item.result_id}`}
        rows={2}
        minLength={5}
        required
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        placeholder="Ex.: confere com o trecho oficial da edição."
      />
      {error ? (
        <p className="status-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="actions-row">
        <button
          type="button"
          disabled={busy || rationale.trim().length < 5}
          onClick={() => void decide("approved")}
        >
          Aprovar e publicar
        </button>
        <button
          type="button"
          className="destructive"
          disabled={busy || rationale.trim().length < 5}
          onClick={() => void decide("rejected")}
        >
          Rejeitar
        </button>
      </div>
      <p className="meta">
        {item.queue_reason === "missing_source_excerpt"
          ? "Atenção: este candidato não trouxe trecho de sustentação; não publique sem localizar o documento. "
          : item.queue_reason === "ai_assistance_pending"
            ? "A IA ainda não respondeu; a decisão deve usar somente o trecho oficial abaixo. "
            : "Trecho e sugestão assistida disponíveis para conferência. "}
        Aprovar publica o ato na página pública /atos, com registro auditado;
        rejeitar mantém fora do site. Extraído por {item.extractor_version} em{" "}
        {new Date(item.result_created_at).toLocaleString("pt-BR")} · artefato{" "}
        {item.artifact_source_url ? (
          <a
            href={item.artifact_source_url}
            target="_blank"
            rel="noreferrer"
          >
            documento oficial
          </a>
        ) : null}{" "}
        {item.artifact_sha256.slice(0, 12)}… · {item.methodology_version}
      </p>
    </article>
  );
}

function FieldList({
  payload,
}: Readonly<{ payload: QueueItem["result_payload"] }>) {
  const fields = payload.fields ?? {};
  return (
    <dl>
      {Object.entries(FIELD_LABELS).map(([key, label]) => {
        const entry = fields[key];
        const isEntry = typeof entry === "object" && entry !== null;
        const found = isEntry && entry.value;
        return (
          <div key={key} style={{ display: "contents" }}>
            <dt>{label}</dt>
            <dd className={found ? undefined : "field-missing"}>
              {found ? entry.value : "não encontrado — confira o trecho"}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

function HistoryCard({
  item,
  onWithdraw,
  busy,
}: {
  item: HistoryItem;
  onWithdraw: (item: HistoryItem, rationale: string) => Promise<string | null>;
  busy: boolean;
}) {
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function withdraw() {
    setError(null);
    const failure = await onWithdraw(item, rationale);
    if (failure) {
      setError(failure);
    } else {
      setConfirming(false);
      setRationale("");
    }
  }

  return (
    <article aria-label="Decisão registrada">
      <div className="card-top">
        <h2>{candidateLabel(item.candidate_type)}</h2>
        <span
          className={
            item.decision === "approved" ? "badge badge-ok" : "badge badge-no"
          }
        >
          {item.decision === "approved"
            ? "Aprovado — público"
            : "Rejeitado — não publicado"}
        </span>
      </div>
      <FieldList payload={item.result_payload} />
      <details>
        <summary>Trecho do documento oficial</summary>
        <pre>{item.result_payload.excerpt ?? "sem trecho"}</pre>
      </details>
      <p className="meta">
        Decidido em {new Date(item.decided_at).toLocaleString("pt-BR")} ·
        justificativa: “{item.rationale}” · artefato{" "}
        {item.artifact_sha256.slice(0, 12)}…
        {item.decision === "approved" ? (
          <>
            {" "}
            ·{" "}
            <a
              className="act-link"
              href={PUBLIC_ACTS_URL}
              target="_blank"
              rel="noreferrer"
            >
              Ver publicado em /atos ↗
            </a>
          </>
        ) : null}
      </p>
      {confirming ? (
        <>
          <label htmlFor={`withdraw-${item.result_id}`}>
            Por que está revertendo? (obrigatório; fica registrado)
          </label>
          <textarea
            id={`withdraw-${item.result_id}`}
            rows={2}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            placeholder="Ex.: aprovei por engano; o trecho é só uma menção."
          />
          {error ? (
            <p className="status-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="actions-row">
            <button
              type="button"
              disabled={busy || rationale.trim().length < 5}
              onClick={() => void withdraw()}
            >
              Confirmar reversão
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setConfirming(false)}
            >
              Cancelar
            </button>
          </div>
        </>
      ) : (
        <div className="actions-row">
          <button
            type="button"
            className="secondary"
            onClick={() => setConfirming(true)}
          >
            Reverter decisão
          </button>
        </div>
      )}
      <p className="meta">
        Reverter não apaga nada: cria um novo registro auditado e devolve o
        candidato à fila para uma nova decisão.
      </p>
    </article>
  );
}

function StatsRow({
  queue,
  history,
}: Readonly<{ queue: QueueState; history: HistoryState }>) {
  const pending = queue.kind === "ready" ? queue.items.length : null;
  const approved =
    history.kind === "ready"
      ? history.items.filter((item) => item.decision === "approved").length
      : null;
  const rejected =
    history.kind === "ready"
      ? history.items.filter((item) => item.decision === "rejected").length
      : null;
  const lastDecision =
    history.kind === "ready" && history.items.length > 0
      ? history.items
          .map((item) => item.decided_at)
          .sort()
          .at(-1)
      : null;

  return (
    <dl className="stats-row" aria-label="Resumo da revisão">
      <div className="stat-card">
        <dt>Aguardando revisão</dt>
        <dd>{pending ?? "—"}</dd>
      </div>
      <div className="stat-card">
        <dt>Aprovados e públicos</dt>
        <dd>{approved ?? "—"}</dd>
      </div>
      <div className="stat-card">
        <dt>Rejeitados</dt>
        <dd>{rejected ?? "—"}</dd>
      </div>
      <div className="stat-card">
        <dt>Última decisão</dt>
        <dd className="stat-date">
          {lastDecision
            ? new Date(lastDecision).toLocaleString("pt-BR", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })
            : "ainda não houve"}
        </dd>
      </div>
    </dl>
  );
}

function TypeChips({
  value,
  onChange,
}: Readonly<{ value: TypeFilter; onChange: (next: TypeFilter) => void }>) {
  const options: readonly (readonly [TypeFilter, string])[] = [
    ["todos", "Todos"],
    ["nomeacao", "Nomeações"],
    ["exoneracao", "Exonerações"],
  ];
  return (
    <div className="chip-group" role="group" aria-label="Filtrar por tipo">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          className={value === key ? "chip chip-active" : "chip"}
          aria-pressed={value === key}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function requiredEnv(value: string | undefined, name: string): string {
  if (!value || value.trim().length === 0) {
    throw new Error(`Variável ${name} ausente no ambiente do admin.`);
  }
  return value;
}

export default function ReviewQueuePage() {
  const supabase = useMemo(
    () =>
      createClient(
        requiredEnv(
          process.env.NEXT_PUBLIC_SUPABASE_URL,
          "NEXT_PUBLIC_SUPABASE_URL",
        ),
        requiredEnv(
          process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
          "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        ),
        // As RPCs curadas vivem no schema `api`, não no `public`.
        { db: { schema: "api" } },
      ),
    [],
  );

  const [session, setSession] = useState<Session | null>(null);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueState>({ kind: "loading" });
  const [history, setHistory] = useState<HistoryState>({ kind: "loading" });
  const [view, setView] = useState<AdminView>("fila");
  const [deciding, setDeciding] = useState(false);
  const [search, setSearch] = useState("");
  const [financeSearch, setFinanceSearch] = useState("");
  const [financeInventory, setFinanceInventory] =
    useState<FinanceInventoryState>({ kind: "loading" });
  const [financeClosures, setFinanceClosures] =
    useState<FinanceClosureState>({ kind: "loading" });
  const [aliasSuggestions, setAliasSuggestions] =
    useState<AliasState>({ kind: "loading" });
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("todos");
  const [decisionFilter, setDecisionFilter] =
    useState<DecisionFilter>("todas");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoaded(true);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange(
      (_event, nextSession) => {
        setSession(nextSession);
      },
    );
    return () => subscription.subscription.unsubscribe();
  }, [supabase]);

  const loadQueue = useCallback(async () => {
    setQueue({ kind: "loading" });
    const { data, error } = await supabase.rpc(
      "get_extraction_review_queue",
      { page_size: 20 },
    );
    if (error) {
      if (error.message.includes("revisores ativos")) {
        setQueue({ kind: "denied" });
        return;
      }
      setQueue({ kind: "error", message: error.message });
      return;
    }
    setQueue({ kind: "ready", items: (data ?? []) as QueueItem[] });
  }, [supabase]);

  const loadHistory = useCallback(async () => {
    setHistory({ kind: "loading" });
    const { data, error } = await supabase.rpc(
      "get_extraction_review_history",
      { page_size: 50 },
    );
    if (error) {
      setHistory({ kind: "error", message: error.message });
      return;
    }
    setHistory({ kind: "ready", items: (data ?? []) as HistoryItem[] });
  }, [supabase]);

  const loadFinanceInventory = useCallback(async () => {
    setFinanceInventory({ kind: "loading" });
    const { data, error } = await supabase.rpc(
      "get_finance_ingestion_inventory",
      { page_size: 500, status_filter: null, resource_filter: null },
    );
    if (error) {
      setFinanceInventory({ kind: "error", message: error.message });
      return;
    }
    setFinanceInventory({
      kind: "ready",
      items: (data ?? []) as FinanceInventoryItem[],
    });
  }, [supabase]);

  const loadFinanceClosures = useCallback(async () => {
    setFinanceClosures({ kind: "loading" });
    const { data, error } = await supabase.rpc(
      "get_public_monthly_finance_closures",
      { page_size: 24, fiscal_year_filter: null },
    );
    if (error) {
      setFinanceClosures({ kind: "error", message: error.message });
      return;
    }
    setFinanceClosures({
      kind: "ready",
      items: (data ?? []) as AdminMonthlyClosure[],
    });
  }, [supabase]);

  const loadAliasSuggestions = useCallback(async () => {
    setAliasSuggestions({ kind: "loading" });
    const { data, error } = await supabase.rpc(
      "get_representative_alias_suggestions",
      { page_size: 50 },
    );
    if (error) {
      if (error.message.includes("revisores ativos")) {
        setAliasSuggestions({ kind: "denied" });
        return;
      }
      setAliasSuggestions({ kind: "error", message: error.message });
      return;
    }
    setAliasSuggestions({
      kind: "ready",
      items: (data ?? []) as AliasSuggestion[],
    });
  }, [supabase]);

  const reloadAll = useCallback(async () => {
    await Promise.all([
      loadQueue(),
      loadHistory(),
      loadFinanceInventory(),
      loadFinanceClosures(),
      loadAliasSuggestions(),
    ]);
  }, [
    loadQueue,
    loadHistory,
    loadFinanceInventory,
    loadFinanceClosures,
    loadAliasSuggestions,
  ]);

  useEffect(() => {
    if (session) {
      void reloadAll();
    }
  }, [session, reloadAll]);

  const decideCandidate = useCallback(
    async (
      item: QueueItem,
      decision: "approved" | "rejected",
      rationale: string,
    ): Promise<string | null> => {
      setDeciding(true);
      try {
        const { error } = await supabase.rpc("review_extraction_candidate", {
          candidate_result_id: item.result_id,
          review_decision: decision,
          review_rationale: rationale,
        });
        if (error) {
          return `A decisão não foi registrada: ${error.message}`;
        }
        await reloadAll();
        return null;
      } finally {
        setDeciding(false);
      }
    },
    [supabase, reloadAll],
  );

  const withdrawDecision = useCallback(
    async (item: HistoryItem, rationale: string): Promise<string | null> => {
      setDeciding(true);
      try {
        const { error } = await supabase.rpc("withdraw_extraction_review", {
          candidate_result_id: item.result_id,
          review_rationale: rationale,
        });
        if (error) {
          return `A reversão não foi registrada: ${error.message}`;
        }
        await reloadAll();
        setView("fila");
        return null;
      } finally {
        setDeciding(false);
      }
    },
    [supabase, reloadAll],
  );

  const reviewAlias = useCallback(
    async (
      item: AliasSuggestion,
      decision: "accepted" | "rejected" | "needs_more_evidence",
      note: string,
    ): Promise<string | null> => {
      setDeciding(true);
      try {
        const { error } = await supabase.rpc(
          "review_representative_alias_suggestion",
          {
            suggestion_id: item.id,
            review_decision: decision,
            review_note: note,
          },
        );
        if (error) return `A revisão do alias não foi registrada: ${error.message}`;
        await loadAliasSuggestions();
        return null;
      } finally {
        setDeciding(false);
      }
    },
    [supabase, loadAliasSuggestions],
  );

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError(null);
    const form = new FormData(event.currentTarget);
    const { error } = await supabase.auth.signInWithPassword({
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    });
    if (error) {
      setLoginError("Não foi possível entrar. Confira e-mail e senha.");
    }
  }

  const visibleQueue = useMemo(() => {
    if (queue.kind !== "ready") {
      return [];
    }
    const term = normalize(search.trim());
    return queue.items.filter((item) => {
      if (typeFilter !== "todos" && item.candidate_type !== typeFilter) {
        return false;
      }
      if (
        term &&
        !payloadSearchText(item.candidate_type, item.result_payload).includes(
          term,
        )
      ) {
        return false;
      }
      return true;
    });
  }, [queue, search, typeFilter]);

  const visibleHistory = useMemo(() => {
    if (history.kind !== "ready") {
      return [];
    }
    const term = normalize(search.trim());
    return history.items.filter((item) => {
      if (decisionFilter !== "todas" && item.decision !== decisionFilter) {
        return false;
      }
      if (typeFilter !== "todos" && item.candidate_type !== typeFilter) {
        return false;
      }
      if (
        term &&
        !normalize(
          `${payloadSearchText(item.candidate_type, item.result_payload)} ${item.rationale}`,
        ).includes(term)
      ) {
        return false;
      }
      return true;
    });
  }, [history, search, typeFilter, decisionFilter]);

  if (!sessionLoaded) {
    return (
      <main>
        <h1>Revisão de candidatos</h1>
        <p aria-live="polite">Carregando sessão…</p>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="login-wrap">
        <form className="login-card" onSubmit={handleLogin} aria-describedby="login-hint">
          <h1>Revisão de candidatos</h1>
          <p id="login-hint" className="page-lede">
            Área interna. Nada aqui é público até ser aprovado por uma pessoa.
            Entre com a conta de revisão cadastrada.
          </p>
          <label htmlFor="email">E-mail</label>
          <input
            id="email"
            autoFocus
            name="email"
            type="email"
            autoComplete="username"
            required
          />
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
          {loginError ? (
            <p className="status-error" role="alert">
              {loginError}
            </p>
          ) : null}
          <button type="submit">Entrar</button>
        </form>
      </main>
    );
  }

  return (
    <main>
      <h1>Revisão de candidatos</h1>
      <p className="page-lede">
        Conectado como {session.user.email} ·{" "}
        <button
          type="button"
          className="secondary"
          style={{ minHeight: "2rem", padding: "0 0.7rem", fontSize: "0.8rem" }}
          onClick={() => void supabase.auth.signOut()}
        >
          Sair
        </button>
      </p>

      {queue.kind === "denied" ? (
        <p className="status-error" role="alert">
          Sua conta não está cadastrada como revisora ativa. O acesso à fila é
          restrito e este bloqueio fica registrado.
        </p>
      ) : (
        <>
          <StatsRow queue={queue} history={history} />

          <nav className="tabs" aria-label="Seções do painel">
            <button
              type="button"
              className={view === "fila" ? "tab tab-active" : "tab"}
              aria-current={view === "fila" ? "page" : undefined}
              onClick={() => setView("fila")}
            >
              Fila
              {queue.kind === "ready" ? ` (${queue.items.length})` : ""}
            </button>
            <button
              type="button"
              className={view === "historico" ? "tab tab-active" : "tab"}
              aria-current={view === "historico" ? "page" : undefined}
              onClick={() => setView("historico")}
            >
              Histórico
              {history.kind === "ready" ? ` (${history.items.length})` : ""}
            </button>
            <button
              type="button"
              className={view === "financas" ? "tab tab-active" : "tab"}
              aria-current={view === "financas" ? "page" : undefined}
              onClick={() => setView("financas")}
            >
              Finanças
              {financeInventory.kind === "ready"
                ? ` (${financeInventory.items.length})`
                : ""}
            </button>
            <button
              type="button"
              className={view === "aliases" ? "tab tab-active" : "tab"}
              aria-current={view === "aliases" ? "page" : undefined}
              onClick={() => setView("aliases")}
            >
              Aliases
              {aliasSuggestions.kind === "ready"
                ? ` (${aliasSuggestions.items.length})`
                : ""}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => void reloadAll()}
            >
              Atualizar
            </button>
          </nav>

          {view !== "financas" && view !== "aliases" ? <div className="toolbar">
            <input
              type="search"
              aria-label="Buscar por pessoa, cargo, órgão ou trecho"
              placeholder="Buscar por pessoa, cargo, órgão ou trecho…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <TypeChips value={typeFilter} onChange={setTypeFilter} />
            {view === "historico" ? (
              <div
                className="chip-group"
                role="group"
                aria-label="Filtrar por decisão"
              >
                {(
                  [
                    ["todas", "Todas"],
                    ["approved", "Aprovadas"],
                    ["rejected", "Rejeitadas"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className={
                      decisionFilter === key ? "chip chip-active" : "chip"
                    }
                    aria-pressed={decisionFilter === key}
                    onClick={() => setDecisionFilter(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
          </div> : null}

          {view === "aliases" ? (
            <AliasReview
              state={aliasSuggestions}
              onReview={reviewAlias}
              busy={deciding}
            />
          ) : view === "financas" ? (
            <FinanceInventory
              state={financeInventory}
              closureState={financeClosures}
              search={financeSearch}
              onSearchChange={setFinanceSearch}
              onReload={() =>
                void Promise.all([loadFinanceInventory(), loadFinanceClosures()])
              }
            />
          ) : view === "fila" ? (
            <>
              {queue.kind === "loading" ? (
                <p aria-live="polite">Carregando fila…</p>
              ) : null}
              {queue.kind === "error" ? (
                <p className="status-error" role="alert">
                  A fila não pôde ser carregada: {queue.message}
                </p>
              ) : null}
              {queue.kind === "ready" && queue.items.length === 0 ? (
                <div className="empty-state">
                  Nenhum candidato aguardando revisão. Fila vazia é um estado
                  legítimo: as edições coletadas não continham atos de pessoal
                  pendentes.
                </div>
              ) : null}
              {queue.kind === "ready" &&
              queue.items.length > 0 &&
              visibleQueue.length === 0 ? (
                <div className="empty-state">
                  Nenhum candidato corresponde à busca ou ao filtro atual.
                </div>
              ) : null}
              {visibleQueue.map((item) => (
                <ReviewCard
                  key={item.result_id}
                  item={item}
                  onDecide={decideCandidate}
                  busy={deciding}
                />
              ))}
            </>
          ) : (
            <>
              {history.kind === "loading" ? (
                <p aria-live="polite">Carregando histórico…</p>
              ) : null}
              {history.kind === "error" ? (
                <p className="status-error" role="alert">
                  O histórico não pôde ser carregado: {history.message}
                </p>
              ) : null}
              {history.kind === "ready" && history.items.length === 0 ? (
                <div className="empty-state">
                  Nenhuma decisão registrada ainda. Tudo o que você aprovar ou
                  rejeitar aparece aqui, com justificativa e data.
                </div>
              ) : null}
              {history.kind === "ready" &&
              history.items.length > 0 &&
              visibleHistory.length === 0 ? (
                <div className="empty-state">
                  Nenhuma decisão corresponde à busca ou ao filtro atual.
                </div>
              ) : null}
              {visibleHistory.map((item) => (
                <HistoryCard
                  key={item.result_id}
                  item={item}
                  onWithdraw={withdrawDecision}
                  busy={deciding}
                />
              ))}
            </>
          )}
        </>
      )}
    </main>
  );
}
