"use client";

import { useCallback, useEffect, useState } from "react";

import type { RpcCall } from "./commitment-link-review";

type Verdict = "correct" | "partial" | "incorrect";

type SampleAct = Readonly<{
  result_id: string;
  act_type: "nomeacao" | "exoneracao";
  published: boolean;
  person_name: string | null;
  position: string | null;
  excerpt: string | null;
}>;

type Annotation = Readonly<{
  act_verdicts: Readonly<Record<string, Verdict>>;
  missed_nomeacoes: number;
  missed_exoneracoes: number;
  note: string | null;
  created_at: string;
  annotator: string;
}>;

type SamplePage = Readonly<{
  sample_page_id: string;
  sample_version: string;
  stratum: string;
  sample_rank: number;
  edition: number;
  edition_year: number;
  page_number: number;
  text_source: "embedded" | "ocr";
  pdf_page_url: string;
  acts: readonly SampleAct[];
  latest_annotation: Annotation | null;
}>;

type Metric = Readonly<{
  scope: string;
  annotated: number;
  sampled: number;
  acts_judged: number;
  missed: number;
  precision_strict: number | string | null;
  precision_lenient: number | string | null;
  recall_estimate: number | string | null;
  methodology_version: string;
}>;

type LoadState =
  | Readonly<{ kind: "loading" }>
  | Readonly<{ kind: "denied" }>
  | Readonly<{ kind: "error"; message: string }>
  | Readonly<{
      kind: "ready";
      pages: readonly SamplePage[];
      metrics: readonly Metric[];
      aiMetrics: readonly Metric[];
    }>;

const ACT_LABELS: Readonly<Record<SampleAct["act_type"], string>> = {
  nomeacao: "Nomeação",
  exoneracao: "Exoneração",
};

const VERDICT_LABELS: Readonly<Record<Verdict, string>> = {
  correct: "Certo",
  partial: "Incompleto",
  incorrect: "Errado",
};

const STRATUM_LABELS: Readonly<Record<string, string>> = {
  act_embedded: "com ato extraído · texto do PDF",
  act_ocr: "com ato extraído · OCR",
  keyword_embedded: "sem ato, com “nomea/exonera” · texto do PDF",
  keyword_ocr: "sem ato, com “nomea/exonera” · OCR",
  other_embedded: "demais páginas · texto do PDF",
  other_ocr: "demais páginas · OCR",
};

// ADR 0091: "ai:<modelo>:<versão do prompt>" ou "human".
function annotatorLabel(annotator: string): string {
  if (!annotator.startsWith("ai:")) return "revisão humana";
  const [, model, prompt] = annotator.split(":");
  return `estimativa automática por IA (${model}, ${prompt}), não revisão humana`;
}

function percent(value: number | string | null): string {
  if (value === null) return "—";
  return `${(Number(value) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

export function ActQualityReview({ rpc }: Readonly<{ rpc: RpcCall }>) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    const [sample, metrics, aiMetrics] = await Promise.all([
      rpc("get_act_quality_sample", {}),
      rpc("get_act_quality_metrics", { p_source: "human" }),
      rpc("get_act_quality_metrics", { p_source: "ai" }),
    ]);
    const error = sample.error ?? metrics.error ?? aiMetrics.error;
    if (error) {
      setState(
        error.message.includes("revisores ativos")
          ? { kind: "denied" }
          : { kind: "error", message: error.message },
      );
      return;
    }
    setState({
      kind: "ready",
      pages: (sample.data ?? []) as SamplePage[],
      metrics: (metrics.data ?? []) as Metric[],
      aiMetrics: (aiMetrics.data ?? []) as Metric[],
    });
  }, [rpc]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(
    async (
      page: SamplePage,
      verdicts: Record<string, Verdict>,
      missedNomeacoes: number,
      missedExoneracoes: number,
      note: string,
    ): Promise<string | null> => {
      const { error } = await rpc("annotate_act_quality_page", {
        p_sample_page_id: page.sample_page_id,
        p_act_verdicts: verdicts,
        p_missed_nomeacoes: missedNomeacoes,
        p_missed_exoneracoes: missedExoneracoes,
        p_note: note,
      });
      if (error) return `A conferência não foi registrada: ${error.message}`;
      await load();
      return null;
    },
    [load, rpc],
  );

  if (state.kind === "loading") {
    return <p aria-live="polite">Carregando a amostra de conferência…</p>;
  }
  if (state.kind === "denied") {
    return (
      <p className="status-error" role="alert">
        Sua conta não está cadastrada como revisora ativa. A amostra permanece restrita.
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="status-error" role="alert">
        A amostra não pôde ser carregada: {state.message}
      </p>
    );
  }
  const done = state.pages.filter((page) => page.latest_annotation !== null).length;
  return (
    <section aria-labelledby="act-quality-title">
      <div className="section-heading-admin">
        <span className="eyebrow-admin">Qualidade da extração</span>
        <h2 id="act-quality-title">Conferência de atos do Diário</h2>
        <p>
          Abra cada página no PDF oficial. Para cada ato que o sistema extraiu,
          marque <strong>Certo</strong> (tipo, pessoa e cargo conferem),{" "}
          <strong>Incompleto</strong> (é o ato, mas falta ou erra um campo) ou{" "}
          <strong>Errado</strong> (não é nomeação/exoneração, ou é do outro tipo).
          Depois conte as nomeações e exonerações da página que o sistema não
          extraiu. Um ato do tipo trocado é “Errado” e também conta como não
          extraído no tipo certo. A conferência não altera nada do que está
          publicado.
        </p>
        <p className="meta">
          {done} de {state.pages.length} páginas conferidas
          {state.pages[0] ? ` · ${state.pages[0].sample_version}` : ""}.
        </p>
      </div>
      <MetricsTable
        metrics={state.metrics}
        caption="Revisão humana: estimativas ponderadas pelos estratos"
      />
      <MetricsTable
        metrics={state.aiMetrics}
        caption="Estimativa automática por IA, não revisão humana (ADR 0091)"
      />
      {state.pages.map((page) => (
        <QualityPageCard key={page.sample_page_id} page={page} onSave={save} />
      ))}
    </section>
  );
}

function MetricsTable({
  metrics,
  caption,
}: Readonly<{ metrics: readonly Metric[]; caption: string }>) {
  const totals = metrics.filter((metric) => metric.scope.startsWith("total:"));
  if (!totals.some((metric) => metric.annotated > 0)) return null;
  return (
    <table>
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Recorte</th>
          <th scope="col">Atos julgados</th>
          <th scope="col">Precisão (certo)</th>
          <th scope="col">Precisão (certo + incompleto)</th>
          <th scope="col">Revocação estimada</th>
        </tr>
      </thead>
      <tbody>
        {totals.map((metric) => (
          <tr key={metric.scope}>
            <th scope="row">
              {metric.scope === "total:overall"
                ? "Todos os atos"
                : ACT_LABELS[metric.scope.replace("total:", "") as SampleAct["act_type"]]}
            </th>
            <td>{metric.acts_judged}</td>
            <td>{percent(metric.precision_strict)}</td>
            <td>{percent(metric.precision_lenient)}</td>
            <td>{percent(metric.recall_estimate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function QualityPageCard({
  page,
  onSave,
}: Readonly<{
  page: SamplePage;
  onSave: (
    page: SamplePage,
    verdicts: Record<string, Verdict>,
    missedNomeacoes: number,
    missedExoneracoes: number,
    note: string,
  ) => Promise<string | null>;
}>) {
  const previous = page.latest_annotation;
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>(
    () => ({ ...(previous?.act_verdicts ?? {}) }),
  );
  const [missedNomeacoes, setMissedNomeacoes] = useState(previous?.missed_nomeacoes ?? 0);
  const [missedExoneracoes, setMissedExoneracoes] = useState(
    previous?.missed_exoneracoes ?? 0,
  );
  const [note, setNote] = useState(previous?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const complete = page.acts.every((act) => verdicts[act.result_id] !== undefined);

  async function submit() {
    setBusy(true);
    setError(null);
    const failure = await onSave(page, verdicts, missedNomeacoes, missedExoneracoes, note);
    if (failure) setError(failure);
    setBusy(false);
  }

  return (
    <article aria-label={`Edição ${page.edition}/${page.edition_year}, página ${page.page_number}`}>
      <div className="card-top">
        <h3>
          Edição {page.edition}/{page.edition_year} · página {page.page_number}
        </h3>
        <span className="badge badge-type">
          {previous ? "conferida" : "pendente"} · {STRATUM_LABELS[page.stratum] ?? page.stratum}
        </span>
      </div>
      {previous ? (
        <p className="meta">Última conferência: {annotatorLabel(previous.annotator ?? "human")}.</p>
      ) : null}
      <p className="meta">
        <a href={page.pdf_page_url} target="_blank" rel="noreferrer">
          Abrir a página {page.page_number} no PDF oficial
        </a>
      </p>
      {page.acts.length === 0 ? (
        <p className="meta">O sistema não extraiu nenhum ato desta página.</p>
      ) : (
        page.acts.map((act) => (
          <fieldset key={act.result_id}>
            <legend>
              {ACT_LABELS[act.act_type]}: {act.person_name ?? "pessoa não identificada"}
              {act.position ? ` · ${act.position}` : ""}
              {act.published ? " · publicado" : ""}
            </legend>
            {act.excerpt ? <p className="meta">“{act.excerpt}”</p> : null}
            {(Object.keys(VERDICT_LABELS) as Verdict[]).map((verdict) => (
              <label key={verdict} className="candidate-option">
                <input
                  type="radio"
                  name={`verdict-${act.result_id}`}
                  value={verdict}
                  checked={verdicts[act.result_id] === verdict}
                  onChange={() =>
                    setVerdicts((current) => ({ ...current, [act.result_id]: verdict }))
                  }
                />{" "}
                {VERDICT_LABELS[verdict]}
              </label>
            ))}
          </fieldset>
        ))
      )}
      <div className="actions-row">
        <label>
          Nomeações não extraídas{" "}
          <input
            type="number"
            min={0}
            max={200}
            value={missedNomeacoes}
            onChange={(event) => setMissedNomeacoes(Math.max(0, Number(event.target.value) || 0))}
          />
        </label>
        <label>
          Exonerações não extraídas{" "}
          <input
            type="number"
            min={0}
            max={200}
            value={missedExoneracoes}
            onChange={(event) =>
              setMissedExoneracoes(Math.max(0, Number(event.target.value) || 0))
            }
          />
        </label>
      </div>
      <label htmlFor={`quality-note-${page.sample_page_id}`}>Observação (opcional)</label>
      <textarea
        id={`quality-note-${page.sample_page_id}`}
        rows={2}
        maxLength={1000}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Ex.: OCR ilegível no pé da página; cargo lido errado."
      />
      {error ? (
        <p className="status-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="actions-row">
        <button type="button" disabled={busy || !complete} onClick={() => void submit()}>
          {previous ? "Registrar nova conferência" : "Registrar conferência"}
        </button>
      </div>
    </article>
  );
}
