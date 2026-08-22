# ADR 0078 — Resumo mensal de despesas por código contábil

## Status

Aceita em 22 de agosto de 2026.

## Contexto

O fechamento mensal exibia os totais do relatório e, em uma sanfona, apenas as
25 maiores linhas pagas. Essa amostra ajuda a investigar valores relevantes,
mas não pode sustentar uma explicação sobre a distribuição completa do mês.
Somá-la no frontend produziria um universo parcial e potencialmente enganoso.

O PDF municipal também encurta algumas descrições por limitação visual da
coluna. O código contábil permanece legível e permite consultar o nome completo
na classificação oficial do Tesouro, sem usar IA para completar texto.

## Decisão

Criar a RPC `api.get_public_expense_category_summary(uuid)`, restrita a um
relatório de despesa vigente, validado, publicado e com vínculo documental
exato. A função:

- agrega todas as linhas do relatório por código contábil usando `numeric`;
- mantém empenho, liquidação e pagamento em colunas separadas;
- conta linhas e variações literais de descrição;
- compara a soma das linhas pagas com o total pago declarado no relatório;
- calcula participação percentual somente quando os valores coincidem
  exatamente;
- expõe uma metodologia versionada e execução apenas para `anon` e
  `authenticated`.

A página mensal mostra o resumo somente para o único relatório que coincide com
a competência fechada. Se a reconciliação falhar, os percentuais e categorias
são ocultados e a divergência é informada. Descrições oficiais só substituem a
forma abreviada quando o código está em lista fechada e o texto municipal é um
prefixo compatível; conflitos preservam a literalidade da Prefeitura.

## Consequências

O cidadão passa a ver a distribuição de todo o relatório, e não somente das 25
maiores linhas. As categorias continuam sendo classificações contábeis: não
representam pagamentos individuais, fornecedores ou prova de entrega do objeto.
Valores negativos legítimos permanecem no agregado e não são rotulados
automaticamente como irregularidade.

## Verificação

- teste PGlite de agregação, reconciliação, metodologia e privilégios;
- contrato estrito do payload PostgREST;
- teste da linguagem pública e do vínculo ao relatório mensal exato;
- testes Node, typecheck, build web e verificação de migrations.
