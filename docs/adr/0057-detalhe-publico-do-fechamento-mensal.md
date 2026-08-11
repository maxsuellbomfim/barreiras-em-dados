# ADR 0057 — Detalhe público do fechamento financeiro mensal

## Status

Aceita em 11 de agosto de 2026.

## Contexto

A página geral de finanças já reúne fechamentos mensais, mas um cartão resumido
não oferece espaço suficiente para explicar os estágios da despesa nem para
mostrar os documentos exatos usados no cálculo. Isso dificulta a conferência
por cidadãos e jornalistas e pode induzir à soma incorreta de empenho,
liquidação e pagamento.

Também não é seguro apresentar receita menos pagamentos como déficit,
superávit, saldo bancário ou dinheiro livre. Essa diferença só é comparável
quando existe uma única versão validada de cada família documental.

## Decisão

Cada competência publicada terá a rota `/financas/AAAA-MM`, sustentada pela RPC
`api.get_public_monthly_finance_detail(date)`.

A RPC:

- aceita somente o primeiro dia de uma competência mensal válida;
- reutiliza o fechamento determinístico versionado;
- expõe apenas documentos validados, publicados e com vínculo exato de origem;
- retorna URLs HTTPS e hashes SHA-256 dos documentos e das respostas brutas;
- não expõe identificadores internos, CPF ou conteúdo bruto sensível;
- executa com `security definer`, `search_path` vazio e permissão explícita para
  `anon` e `authenticated`.

A página:

- apresenta receita declarada, empenho, liquidação e pagamento separadamente;
- informa de modo destacado que os três estágios da despesa não devem ser
  somados;
- só exibe a diferença operacional quando a competência é comparável;
- chama a diferença apenas de “receita declarada menos pagamentos”;
- mantém PDFs, respostas oficiais e hashes acessíveis no próprio mês;
- trata ausência de documento como dado pendente, nunca como valor zero;
- recolhe hashes e metodologia em elementos expansíveis para preservar a
  leitura popular sem esconder a auditoria.

## Consequências

O fechamento passa a ser verificável sem transformar a página geral em uma
lista técnica extensa. Meses duplicados ou incompletos continuam públicos como
cobertura documental, mas não produzem uma diferença potencialmente enganosa.

Esta decisão não consolida dívida, restos a pagar, disponibilidade de caixa ou
resultado fiscal. Esses conceitos exigem fontes e reconciliações próprias.

## Verificação

- teste PGlite da RPC, privilégios e linhagem;
- contrato estrito do payload público;
- testes da linguagem por estado do fechamento;
- typecheck, build e testes web;
- revisão de teclado, foco, contraste, títulos e ordem de leitura.
