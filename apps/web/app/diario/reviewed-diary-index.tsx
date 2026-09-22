import type { IntegralGazetteEdition } from "../../lib/integral-gazette-documents";
import review from "./reviewed-4310.json";

export function ReviewedDiaryIndex({ edition }: { edition: IntegralGazetteEdition }) {
  if (
    edition.artifactSha256 !== review.sha256 ||
    edition.edition !== review.edition ||
    edition.editionYear !== review.year
  ) return null;

  return (
    <section className="collection-unavailable reviewed-diary-index" aria-labelledby="reviewed-pages-title">
      <div>
        <h2 id="reviewed-pages-title">Encontre cada documento no PDF oficial</h2>
        <p>
          15 documentos, das páginas 1 a 137. Os limites foram conferidos
          visualmente no arquivo preservado. Os títulos abaixo são abreviados
          para navegação; não substituem o texto oficial.
        </p>
        <p>
          Cada link abre o PDF completo na página inicial do documento. Se o
          leitor do seu celular não avançar automaticamente, use o intervalo
          indicado. Não são arquivos separados nem uma aprovação do texto extraído.
        </p>
        <ol>
          {review.documents.map((document) => (
            <li key={document.start}>
              <a href={`${review.url}#page=${document.start}`} target="_blank" rel="noreferrer">
                {document.title} — {document.start === document.end
                  ? `página ${document.start}`
                  : `páginas ${document.start} a ${document.end}`} (PDF, nova aba)
              </a>
            </li>
          ))}
        </ol>
        <p>Atas de registro de preços não comprovam, por si só, compras ou pagamentos realizados.</p>
      </div>
    </section>
  );
}
