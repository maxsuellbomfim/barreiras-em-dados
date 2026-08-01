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

const FIELD_LABELS: Readonly<Record<string, string>> = {
  person_name: "Pessoa",
  position: "Cargo",
  position_symbol: "Símbolo",
  organization: "Órgão",
  act_number: "Portaria nº",
  act_date: "Data do ato",
};

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
      <h2>
        {item.candidate_type === "nomeacao"
          ? "Nomeação"
          : item.candidate_type === "exoneracao"
            ? "Exoneração"
            : item.candidate_type}
      </h2>
      <FieldList payload={item.result_payload} />
      <details>
        <summary>Trecho do documento oficial</summary>
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
      <p>
        <button
          type="button"
          disabled={busy || rationale.trim().length < 5}
          onClick={() => void decide("approved")}
        >
          Aprovar
        </button>{" "}
        <button
          type="button"
          className="secondary"
          disabled={busy || rationale.trim().length < 5}
          onClick={() => void decide("rejected")}
        >
          Rejeitar
        </button>
      </p>
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
        return (
          <div key={key} style={{ display: "contents" }}>
            <dt>{label}</dt>
            <dd>
              {isEntry && entry.value
                ? entry.value
                : "não encontrado — confira o trecho"}
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
        <h2>
          {item.candidate_type === "nomeacao"
            ? "Nomeação"
            : item.candidate_type === "exoneracao"
              ? "Exoneração"
              : item.candidate_type}
        </h2>
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
          <p>
            <button
              type="button"
              disabled={busy || rationale.trim().length < 5}
              onClick={() => void withdraw()}
            >
              Confirmar reversão
            </button>{" "}
            <button
              type="button"
              className="secondary"
              onClick={() => setConfirming(false)}
            >
              Cancelar
            </button>
          </p>
        </>
      ) : (
        <p>
          <button
            type="button"
            className="secondary"
            onClick={() => setConfirming(true)}
          >
            Reverter decisão
          </button>
        </p>
      )}
      <p className="meta">
        Reverter não apaga nada: cria um novo registro auditado e devolve o
        candidato à fila para uma nova decisão.
      </p>
    </article>
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
      <main>
        <h1>Revisão de candidatos</h1>
        <p className="meta">
          Área interna. Nada aqui é público até ser aprovado por uma pessoa.
        </p>
        <form onSubmit={handleLogin} aria-describedby="login-hint">
          <p id="login-hint" className="meta">
            Entre com a conta de revisão cadastrada.
          </p>
          <label htmlFor="email">E-mail</label>
          <input
            id="email"
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
      <p className="meta">
        Conectado como {session.user.email}.{" "}
        <button
          type="button"
          className="secondary"
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
                <p>
                  Nenhum candidato aguardando revisão. Fila vazia é um estado
                  legítimo: as edições coletadas não continham atos de
                  pessoal pendentes.
                </p>
              ) : null}
              {queue.kind === "ready"
                ? queue.items.map((item) => (
                    <ReviewCard
                      key={item.result_id}
                      item={item}
                      onDecide={decideCandidate}
                      busy={deciding}
                    />
                  ))
                : null}
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
                <p>
                  Nenhuma decisão registrada ainda. Tudo o que você aprovar
                  ou rejeitar aparece aqui, com justificativa e data.
                </p>
              ) : null}
              {history.kind === "ready"
                ? history.items.map((item) => (
                    <HistoryCard
                      key={item.result_id}
                      item={item}
                      onWithdraw={withdrawDecision}
                      busy={deciding}
                    />
                  ))
                : null}
            </>
          )}
        </>
      )}
    </main>
  );
}
