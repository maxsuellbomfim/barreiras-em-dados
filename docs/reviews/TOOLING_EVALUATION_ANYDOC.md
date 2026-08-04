# Avaliação do AnyDoc

Data: 2026-08-04

## Decisão provisória

Adicionar um adaptador opcional e um benchmark, sem substituir o parser atual
nem enviar documentos públicos a serviço externo. A ativação em produção exige
comparação com um corpus de 20 documentos reais e replay reproduzível.

## Encaixe no Barreiras 360

O `firecrawl-anydoc` converte documentos de escritório, PDF e CSV para Markdown
por meio de um modelo estrutural comum. A maior oportunidade está em DOCX,
XLSX, ODT e editais que hoje não entram no fluxo de extração. A saída é útil
para busca, visualização e IA assistida; não é fonte de cálculo financeiro.

Para PDFs, AnyDoc usa o `pdf-inspector`. PDFs escaneados continuam exigindo
OCR. Por isso o pipeline mantém a classificação, o OCR e a preservação bruta
existentes.

## Critérios do benchmark

Para cada arquivo público:

- detecção correta do formato;
- presença de títulos, listas e tabelas;
- preservação de valores e separadores decimais;
- hash do bruto e da saída derivada;
- tempo e tamanho da saída;
- replay idempotente;
- comportamento em PDF escaneado, arquivo truncado e planilha malformada.

O benchmark não imprime conteúdo documental. O adaptador grava somente hashes,
versão do parser, tamanhos, formato e latência.

## Regras de adoção

1. AnyDoc local é um parser derivado, nunca a fonte bruta.
2. Valores financeiros são calculados de células/contratos normalizados por
   código determinístico, nunca de Markdown ou modelo de linguagem.
3. Cada saída recebe `parser_version` e hash próprios.
4. Falha ou baixa cobertura aciona o parser atual/OCR, sem bloquear a coleta.
5. O `/parse` hospedado só será fallback explícito, com credencial separada,
   limite de tamanho, registro de envio e Zero Data Retention habilitado.

## Próxima etapa

Popular `fixtures/anydoc` com 20 documentos oficiais revisados e executar o
benchmark em CI e localmente. Só depois decidir se o AnyDoc entra no caminho de
DOCX/XLSX e se vale um fallback remoto para PDFs escaneados.
