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

const FIELD_LABELS: Readonly<Record<string, string>> = {
  person_name: "Pessoa",
  position: "Cargo",
  position_symbol: "Símbolo",
  organization: "Órgão",
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
  const fields = item.result_payload.fields ?? {};

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
        Aprovar registra sua decisão com auditoria; a publicação no site é uma
        etapa separada. Extraído por {item.extractor_version} em{" "}
        {new Date(item.result_created_at).toLocaleString("pt-BR")} · artefato{" "}
        {item.artifact_sha256.slice(0, 12)}… · {item.methodology_version}
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

  useEffect(() => {
    if (session) {
      void loadQueue();
    }
  }, [session, loadQueue]);

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
        await loadQueue();
        return null;
      } finally {
        setDeciding(false);
      }
    },
    [supabase, loadQueue],
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

      {queue.kind === "loading" ? (
        <p aria-live="polite">Carregando fila…</p>
      ) : null}

      {queue.kind === "denied" ? (
        <p className="status-error" role="alert">
          Sua conta não está cadastrada como revisora ativa. O acesso à fila é
          restrito e este bloqueio fica registrado.
        </p>
      ) : null}

      {queue.kind === "error" ? (
        <p className="status-error" role="alert">
          A fila não pôde ser carregada: {queue.message}
        </p>
      ) : null}

      {queue.kind === "ready" && queue.items.length === 0 ? (
        <p>
          Nenhum candidato aguardando revisão. Fila vazia é um estado
          legítimo: as edições coletadas não continham atos de pessoal.
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
    </main>
  );
}
