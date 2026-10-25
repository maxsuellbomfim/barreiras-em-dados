# Finanças: catálogo de documentos e números validados

## Diagnóstico

A API de dados abertos da Prefeitura responde aos recursos financeiros com um
catálogo de documentos. Uma amostra observada em 02/08/2026 retornou campos como
`titulo`, `data`, `ano`, `mes`, `descricao` e `url` para
`pdc-resumo-execucao-da-receita`; ela não retornou um campo numérico de receita.

Por isso, a página pública não deve fabricar totais a partir do título ou do
nome do arquivo. O fluxo correto é:

```text
API municipal → resposta bruta preservada → documento oficial → extração
validada → revisão → finance.revenues → projeção pública
```

## O que foi implementado

- catálogo municipal versionado em `fixtures/sources/municipal-source-catalog.json`;
- schema e verificação de fontes no CI;
- função `api.get_public_finance_documents`;
- página `/financas` com duas camadas:
  - números somente quando `finance.revenues` estiver normalizada;
  - documentos oficiais e trilha de evidência quando a fonte ainda for PDF;
- workflow diário para preservar os catálogos financeiros da Prefeitura;
- preservação do PDF apontado por cada registro como artefato filho imutável,
  com allowlist exclusiva de `barreiras.mtransparente.com.br`, hash e vínculo
  ao artefato JSON pai;
- associação exata entre registro e PDF por `source_record_key`, impedindo que
  relatórios distintos de uma mesma resposta da API compartilhem por engano o
  artefato filho mais recente;
- parser determinístico inicial para o `Demonstrativo de Receita Orçamentária
  Sintético`, com suporte a valores negativos de deduções e testes unitários;
- contrato de assistência em cascata para classificar o relatório e sugerir
  linhas com âncora literal, sem permitir que a IA calcule números;
- contrato publicável e publicador idempotente para o primeiro demonstrativo de
  receita, com deduções assinadas e status `validated`;
- workflow separado para publicar uma janela financeira por ano, com backfill
  inicial a partir de 2021;
- mensagem pública explícita quando a ausência de números ainda for uma
  etapa de validação, e não receita zero.
- busca probatória no catálogo completo de balancetes, com resultado mensal
  `found` ou `not_found`, respostas brutas vinculadas e manifesto SHA-256;
- projeção pública distinta para “não encontrado no catálogo oficial”, sem
  confundir essa evidência temporal com valor zero ou inexistência definitiva.
- cobertura desacoplada do download: o catálogo completo é registrado primeiro
  e os PDFs de balancetes são drenados em lotes retomáveis de cinco arquivos.

## Limite atual

### Consulta por ano e paginação — 25/10/2026

`/financas/documentos` usa `api.get_public_finance_document_page`, migration
aditiva `20261025051028`. A consulta seleciona a versão mais recente de cada
chave oficial antes do filtro de ano; calcula o total do recorte sem limitar
o catálogo aos primeiros 200 e só busca o PDF vinculado para a página de 25
referências. A seleção permite ano e família; anos não informados continuam
acessíveis em “Todos os anos”. O total é de referências preservadas, não de
PDFs únicos nem prova de cobertura completa do portal municipal.

Conferência anônima em produção: 2021 retornou 27 referências, distribuídas em
25 e 2. Teste de banco cobre 210 referências, versão que muda de ano, página
vazia, filtros inválidos e ausência de acesso anônimo ao bruto. Falha de
consulta não vira lista vazia; os calendários anteriores mantêm limites
explícitos e ganham link para esta exploração.

O dry-run da CLI detectou a migration remota histórica `20260923181039`
(`approved_acts_text_source`) ausente localmente. Não foi reparada/revertida
nem reescrita. A nova função foi aplicada isoladamente pela integração oficial,
e o arquivo local recebeu a mesma versão registrada no banco. A reconciliação
da migration histórica continua separada desta entrega.

### Instalação e recuperação operacional — 15/09/2026

Na execução `34952573445`, balancetes não chegou à coleta: a instalação não
encontrou `cryptography==50.0.0`. Outro job do mesmo commit/Python instalou a
mesma versão; não foi comprovado pin inválido. O helper stdlib
`scripts/install_collector_dependencies.py` repete somente o comando fixo
`.[postgres,storage]`, no máximo três vezes, com limite de 180 segundos por
processo e esperas de 5/10 segundos. Mantém a saída original do pip e o último
código não zero; timeout termina com 124 e falha ao iniciar com 127.
Não recebe comandos nem configurações livres. As seis instalações idênticas
do workflow financeiro o reutilizam; o passo com extras PDF não mudou.

Sucesso na instalação não comprova coleta. A recuperação deve executar somente
balancetes, mantendo catálogo completo e drenagem limitada/checkpoint dos PDFs.
Contadores de catálogo, documentos preservados, falhas e limites precisam ser
conferidos antes de informar cobertura. Não é necessário reexecutar toda a
matriz nem fontes que já concluíram.

O workflow preserva a resposta da API e o PDF oficial quando o endpoint entrega
um link válido. O publicador grava somente linhas com validação determinística,
preserva a direção contábil das deduções e liga cada linha ao JSON pai e ao PDF
filho.

Versões publicadas antes do vínculo exato são mantidas imutáveis e entram em
auditoria de evidência. Qualquer correção será uma nova versão rastreável, nunca
uma atualização silenciosa do registro histórico.

O parser inicial reconhece o layout textual desse demonstrativo quando o PDF
passa pelo extrator de texto. Páginas sem texto embutido permanecem fora da
publicação até o estágio de OCR; elas não são tratadas como receita zero.

## Procedimento de ativação

1. Aplicar as migrations `20260804030000_public_finance_documents.sql`,
   `20260804040000_finance_document_artifacts.sql` e
   `20260805010000_finance_revenue_automation.sql` no projeto Supabase de
   produção.
2. Conferir se as variáveis e secrets usados pelo workflow municipal continuam
   válidos.
3. Executar manualmente `Coletar documentos financeiros municipais` para uma
   matriz pequena e revisar o status da coleta.
4. Executar `Publicar receitas financeiras validadas` com `limit=1` e o ano do
   primeiro relatório coletado.
5. Conferir `/financas`; somente linhas `validated` devem aparecer, com PDF,
   hash, direção contábil e metodologia.
6. Ampliar o backfill por ano após conferir a primeira janela; anos sem fonte
   validada devem continuar visíveis como ausência de cobertura, não como zero.
