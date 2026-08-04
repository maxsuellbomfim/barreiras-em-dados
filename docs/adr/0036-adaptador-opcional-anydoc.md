# ADR 0036 — Adaptador opcional AnyDoc

- **Status:** aceito para experimento
- **Data:** 2026-08-04

## Contexto

O Barreiras 360 precisa lidar com editais, planilhas, contratos e PDFs em
formatos variados. O parser atual cobre PDF e OCR, mas ainda não oferece uma
camada uniforme para DOCX/XLSX/ODT/CSV.

## Decisão

Usar `firecrawl-anydoc` apenas por meio de um adaptador opcional no worker de
documentos. A conversão gera texto derivado e hashes; o bruto, a extração
determinística e a evidência literal permanecem no pipeline atual.

## Consequências

- o pacote não é instalado no caminho padrão sem o extra `anydoc`;
- o benchmark pode ser executado sem publicar conteúdo;
- PDFs escaneados continuam indo para OCR;
- a versão do parser precisa ser registrada para permitir replay;
- o `/parse` remoto não entra no caminho padrão.

## Reversão

Remover o extra e o adaptador não altera o schema nem os artefatos brutos; o
parser PDF/OCR existente continua sendo o fallback oficial.
