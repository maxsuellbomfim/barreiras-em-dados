"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import type { FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";

type AdminAuthClient = Pick<SupabaseClient, "auth">;

type GateState =
  | { kind: "checking" }
  | { kind: "error"; message: string }
  | { kind: "unenrolled" }
  | { kind: "enrolling"; factorId: string; qrCode: string; secret: string }
  | { kind: "challenge"; factorId: string }
  | { kind: "verified" };

function qrCodeSource(value: string): string {
  if (value.startsWith("data:")) return value;
  return `data:image/svg+xml;utf-8,${encodeURIComponent(value)}`;
}

function verificationCode(form: HTMLFormElement): string {
  return String(new FormData(form).get("verification-code") ?? "")
    .replace(/\D/g, "")
    .slice(0, 8);
}

export function AdminMfaGate({
  client,
  sessionKey,
  children,
}: Readonly<{
  client: AdminAuthClient;
  sessionKey: string;
  children: ReactNode;
}>) {
  const [state, setState] = useState<GateState>({ kind: "checking" });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refreshAssurance = useCallback(async () => {
    setState({ kind: "checking" });
    setActionError(null);

    const { data: assurance, error: assuranceError } =
      await client.auth.mfa.getAuthenticatorAssuranceLevel();
    if (assuranceError) {
      setState({
        kind: "error",
        message: "Não foi possível verificar a proteção da sessão.",
      });
      return;
    }

    if (assurance.currentLevel === "aal2") {
      setState({ kind: "verified" });
      return;
    }

    if (assurance.nextLevel === "aal2") {
      const { data: factors, error: factorsError } =
        await client.auth.mfa.listFactors();
      const factor = factors?.totp.at(0);
      if (factorsError || !factor) {
        setState({
          kind: "error",
          message: "O segundo fator existe, mas não pôde ser carregado.",
        });
        return;
      }
      setState({ kind: "challenge", factorId: factor.id });
      return;
    }

    setState({ kind: "unenrolled" });
  }, [client]);

  useEffect(() => {
    void refreshAssurance();
  }, [refreshAssurance, sessionKey]);

  async function startEnrollment() {
    setBusy(true);
    setActionError(null);
    try {
      const { data, error } = await client.auth.mfa.enroll({
        factorType: "totp",
        friendlyName: "Barreiras 360 - painel de revisão",
        issuer: "Barreiras 360",
      });
      if (error || !data) {
        setActionError("Não foi possível iniciar a configuração do MFA.");
        return;
      }
      setState({
        kind: "enrolling",
        factorId: data.id,
        qrCode: data.totp.qr_code,
        secret: data.totp.secret,
      });
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.kind !== "enrolling" && state.kind !== "challenge") return;

    const code = verificationCode(event.currentTarget);
    if (code.length < 6) {
      setActionError("Informe o código completo do aplicativo autenticador.");
      return;
    }

    setBusy(true);
    setActionError(null);
    try {
      const { error } = await client.auth.mfa.challengeAndVerify({
        factorId: state.factorId,
        code,
      });
      if (error) {
        setActionError("Código inválido ou expirado. Gere um novo e tente novamente.");
        return;
      }
      await refreshAssurance();
    } finally {
      setBusy(false);
    }
  }

  async function cancelEnrollment() {
    if (state.kind !== "enrolling") return;
    setBusy(true);
    setActionError(null);
    try {
      const { error } = await client.auth.mfa.unenroll({
        factorId: state.factorId,
      });
      if (error) {
        setActionError("Não foi possível cancelar esta configuração.");
        return;
      }
      setState({ kind: "unenrolled" });
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "checking") {
    return (
      <main className="login-wrap">
        <p aria-live="polite">Verificando proteção da sessão…</p>
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="login-wrap">
        <section className="login-card" aria-labelledby="mfa-error-title">
          <h1 id="mfa-error-title">Proteção da sessão indisponível</h1>
          <p className="status-error" role="alert">
            {state.message}
          </p>
          <button type="button" onClick={() => void refreshAssurance()}>
            Tentar novamente
          </button>
        </section>
      </main>
    );
  }

  if (state.kind === "challenge" || state.kind === "enrolling") {
    const enrolling = state.kind === "enrolling";
    return (
      <main className="login-wrap">
        <section className="login-card mfa-card" aria-labelledby="mfa-title">
          <h1 id="mfa-title">
            {enrolling ? "Proteja sua conta" : "Confirme o segundo fator"}
          </h1>
          <p className="page-lede">
            {enrolling
              ? "Leia o QR code no aplicativo autenticador e informe o código gerado."
              : "Abra o aplicativo autenticador cadastrado e informe o código atual."}
          </p>

          {enrolling ? (
            <div className="mfa-enrollment-secret">
              <img
                className="mfa-qr-code"
                src={qrCodeSource(state.qrCode)}
                alt="QR code para cadastrar o segundo fator"
              />
              <p className="meta">
                Se não puder ler o QR code, digite esta chave no autenticador:
              </p>
              <code className="mfa-secret">{state.secret}</code>
            </div>
          ) : null}

          <form onSubmit={verifyCode}>
            <label htmlFor="verification-code">Código do autenticador</label>
            <input
              id="verification-code"
              name="verification-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9 ]{6,8}"
              minLength={6}
              maxLength={8}
              required
              autoFocus={!enrolling}
            />
            {actionError ? (
              <p className="status-error" role="alert">
                {actionError}
              </p>
            ) : null}
            <div className="actions-row">
              <button type="submit" disabled={busy}>
                {busy ? "Verificando…" : "Confirmar código"}
              </button>
              {enrolling ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => void cancelEnrollment()}
                >
                  Configurar depois
                </button>
              ) : null}
            </div>
          </form>
        </section>
      </main>
    );
  }

  return (
    <>
      {state.kind === "unenrolled" ? (
        <aside className="mfa-notice" aria-labelledby="mfa-notice-title">
          <div>
            <strong id="mfa-notice-title">Sua conta ainda não usa MFA</strong>
            <p>
              Cadastre um aplicativo autenticador. Nesta primeira fase, o acesso
              continua disponível enquanto os revisores concluem a adesão.
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void startEnrollment()}
          >
            {busy ? "Preparando…" : "Configurar MFA"}
          </button>
          {actionError ? (
            <p className="status-error" role="alert">
              {actionError}
            </p>
          ) : null}
        </aside>
      ) : null}
      {children}
    </>
  );
}
