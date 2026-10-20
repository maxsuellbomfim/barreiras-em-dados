import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { normalizeTargetPath, submitContestation } from "../../lib/contestations.mjs";

export const metadata: Metadata = {
  title: "Contestar uma informação",
  description:
    "Formulário anônimo para contestar um dado, indício ou texto publicado no Barreiras 360. Cada contestação recebe protocolo e faz o caso ser conferido de novo.",
};

type PageProps = Readonly<{ searchParams: Promise<{ url?: string; erro?: string }> }>;

async function sendContestation(formData: FormData) {
  "use server";
  // Campo invisível: pessoas deixam em branco, robôs preenchem.
  if (String(formData.get("site") ?? "").trim()) redirect("/contestar?erro=envio");

  const rawPath = String(formData.get("pagina") ?? "");
  const targetPath = normalizeTargetPath(rawPath);
  if (!targetPath) {
    redirect(`/contestar?erro=pagina&url=${encodeURIComponent(rawPath.slice(0, 300))}`);
  }
  const result = await submitContestation({
    targetPath,
    description: String(formData.get("descricao") ?? ""),
    evidenceUrl: String(formData.get("evidencia") ?? "").trim() || null,
    contact: String(formData.get("contato") ?? "").trim() || null,
  });
  if (result.state === "created") redirect(`/contestar/${result.protocol}`);
  const reason = result.state === "invalid" ? "dados" : "indisponivel";
  redirect(`/contestar?erro=${reason}&url=${encodeURIComponent(targetPath)}`);
}

const ERRORS: Record<string, string> = {
  pagina: "Informe a página contestada: um endereço deste site ou um caminho como /indicios.",
  dados:
    "Confira os campos: a descrição precisa ter entre 10 e 4000 caracteres e o link de evidência deve começar com https://.",
  indisponivel:
    "Não foi possível registrar agora. Tente de novo em alguns minutos; nada foi gravado.",
  envio: "Não foi possível registrar o envio.",
};

export default async function ContestPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const prefill = normalizeTargetPath(params.url ?? "") ?? "";
  const error = params.erro ? ERRORS[params.erro] : undefined;

  return (
    <main>
      <section className="section" aria-labelledby="contest-title">
        <div className="section-heading">
          <span className="eyebrow">Correção e direito de resposta</span>
          <h1 id="contest-title">Contestar uma informação</h1>
          <p>
            Encontrou um erro, tem um documento que explica um indício ou quer registrar uma
            resposta? Envie por aqui. <strong>Não pedimos login nem identificação.</strong> Cada
            contestação recebe um protocolo e faz o caso ser conferido de novo contra a fonte
            oficial; se a evidência não se sustentar, o conteúdo é corrigido ou retirado, e a
            correção fica registrada.
          </p>
        </div>

        {error ? (
          <div className="collection-unavailable" role="alert">
            <div>
              <strong>Contestação não enviada</strong>
              <p>{error}</p>
            </div>
          </div>
        ) : null}

        <form action={sendContestation} className="contest-form">
          <label>
            Página contestada
            <input
              name="pagina"
              type="text"
              required
              maxLength={300}
              defaultValue={prefill}
              placeholder="/indicios ou o endereço completo da página"
            />
          </label>
          <label>
            O que está errado ou o que precisa ser considerado
            <textarea name="descricao" required minLength={10} maxLength={4000} rows={7} />
          </label>
          <label>
            Link para documento que comprove (opcional)
            <input name="evidencia" type="url" maxLength={500} placeholder="https://" />
          </label>
          <label>
            Contato para retorno (opcional, nunca publicado)
            <input name="contato" type="text" maxLength={200} autoComplete="off" />
          </label>
          <label className="contest-honeypot" aria-hidden="true">
            Não preencha
            <input name="site" type="text" tabIndex={-1} autoComplete="off" />
          </label>
          <button type="submit">Enviar contestação</button>
        </form>

        <p className="hero-note">
          O texto e o contato ficam guardados só para analisar o pedido e não aparecem no site; a
          consulta pelo protocolo mostra apenas a página, o andamento e a resolução. Não envie
          dados pessoais de terceiros nem documentos sigilosos. Veja o{" "}
          <a href="/privacidade">aviso de privacidade</a>.
        </p>
      </section>
    </main>
  );
}
