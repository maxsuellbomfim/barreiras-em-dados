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
        Aprovar publica o ato na página pública /atos, com registro auditado;
        rejeitar mantém fora do site. Extraído por {item.extractor_version} em{" "}
        {new Date(item.result_created_at).toLocaleString("pt-BR")} · artefato{" "}
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
        <dt>Aprovados no histórico</dt>
        <dd>{approved ?? "—"}</dd>
      </div>
      <div className="stat-card">
        <dt>Rejeitados no histórico</dt>
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
  const [view, setView] = useState<"fila" | "historico">("fila");
  const [deciding, setDeciding] = useState(false);
  const [search, setSearch] = useState("");
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
      { page_size: 100 },
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
      { page_size: 200 },
    );
    if (error) {
      setHistory({ kind: "error", message: error.message });
      return;
    }
    setHistory({ kind: "ready", items: (data ?? []) as HistoryItem[] });
  }, [supabase]);

  const reloadAll = useCallback(async () => {
    await Promise.all([loadQueue(), loadHistory()]);
  }, [loadQueue, loadHistory]);

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
              className="secondary"
              onClick={() => void reloadAll()}
            >
              Atualizar
            </button>
          </nav>

          <div className="toolbar">
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
          </div>

          {view === "fila" ? (
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
