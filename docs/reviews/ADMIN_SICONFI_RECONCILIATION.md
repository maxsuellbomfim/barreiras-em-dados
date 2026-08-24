# Conferência SICONFI no painel administrativo

## Objetivo

O painel de finanças passa a mostrar a reconciliação determinística entre a
DCA anual do SICONFI e os doze fechamentos mensais publicados pela Prefeitura.
A finalidade é permitir que a equipe identifique lacunas e diferenças antes de
tratar um exercício como historicamente estabilizado.

## Comportamento

- empenhado, liquidado e pago permanecem métricas independentes;
- valores são recebidos da RPC como decimais exatos e apenas formatados pela
  interface;
- diferenças recebem prioridade visual, mas não são classificadas como erro,
  déficit ou irregularidade;
- uma série com menos de doze competências não exibe soma parcial comparável;
- os meses ausentes aparecem por nome;
- payload incompatível com o contrato falha fechado e gera estado de erro no
  painel, em vez de produzir indicadores parciais.

## Verificação operacional em 24 de agosto de 2026

A RPC de produção retornou cinco exercícios. A consulta confirmou a existência
de correspondências exatas, diferenças entre fontes e coberturas incompletas.
Em particular, o exercício de 2023 ainda não contém abril e 2021 permanece sem
competências mensais publicadas na projeção. Esses estados são lacunas de
cobertura a resolver; não significam despesa zero.

## Limitações e próxima ação

O painel diagnostica, mas não corrige a cobertura. A próxima menor etapa
vertical é localizar e preservar o relatório municipal de abril de 2023 e,
depois, executar o backfill mensal de 2021 com checkpoints e evidência de
ausência quando a fonte oficial não disponibilizar determinado documento.
