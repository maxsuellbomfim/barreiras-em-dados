# ADR 0018 — Sinais financeiros determinísticos para contexto

## Status

Aceito — primeira versão operacional.

## Contexto

O portal já publica relatórios de despesa validados, mas ainda precisava mostrar
quando uma leitura exige reconciliação. Uma anomalia não pode ser apresentada
como prova de fraude ou corrupção e não pode depender de um modelo de linguagem
para calcular valores.

## Decisão

Adicionar duas regras versionadas em `analysis.anomaly_rules`:

1. mais de um relatório validado para o mesmo órgão e período;
2. relação contábil que pede conferência (pagamento ou liquidação acumulados
   acima do empenhado acumulado, ou total negativo).

`analysis.refresh_finance_signals()` calcula os sinais com SQL determinístico,
é idempotente e cria uma evidência de cálculo vinculada ao registro bruto. A
projeção `api.get_public_finance_signals` expõe somente sinais em triagem ou
contexto, com explicação neutra, período e fonte.

## Consequências

- O cidadão vê o que merece conferência sem receber acusação automática.
- A equipe pode revisar, contextualizar, descartar ou superseder cada finding
  preservando o histórico.
- A IA continua opcional para explicações; os cálculos e a classificação inicial
  são reproduzíveis por código.
- As regras são deliberadamente conservadoras. Novas regras só entram após
  fixture, teste e revisão metodológica.

## Próxima etapa

Adicionar cobertura mensal explícita (meses sem relatório e fontes esperadas) e
depois cruzar sinais com itens de compras, contratos e fornecedores.
