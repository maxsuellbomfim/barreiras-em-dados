// Avisos públicos sobre PDFs da folha com decisão registrada. A chave é o hash
// do documento, o mesmo usado pelo publicador em
// ACCEPTED_DECLARED_MONTH_DIVERGENCES (docs/reviews/PAYROLL_2023_03_DECLARED_MONTH.md).
export const PAYROLL_DOCUMENT_NOTES = new Map([
  [
    "11a6f1365797c296bceb4471b5ec66f8922bb1a0599d5a4e97d22d0a595c15cb",
    {
      title: "O cabeçalho deste PDF diz “Abril / 2023”",
      body:
        "Tratamos o documento como a folha de março de 2023: o portal da Prefeitura o publica como março e ele foi emitido em 04/04/2023, antes do fechamento de abril (a folha de abril saiu em 05/05/2023). Nenhum dos 73 relatórios conferidos foi emitido dentro do próprio mês de referência. Os valores são os do PDF, sem ajuste.",
    },
  ],
]);

export function payrollDocumentNotes(documents) {
  return documents
    .map((document) => PAYROLL_DOCUMENT_NOTES.get(document.artifactSha256))
    .filter(Boolean);
}
