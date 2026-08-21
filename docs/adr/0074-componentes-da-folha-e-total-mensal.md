# ADR 0074 — Componentes da folha e total mensal

## Status

Aceita em 22 de agosto de 2026.

## Contexto

O catálogo oficial pode publicar mais de um PDF de folha na mesma competência.
A inspeção dos documentos de junho e dezembro de 2024 e 2025 comprovou que eles
não são necessariamente retificações: há folhas regulares, adiantamentos do
13º salário e parcelas finais do 13º salário. Substituir um arquivo pelo outro
apagaria parte do custo oficial do mês; somar a quantidade de vínculos de todos
eles contaria algumas pessoas mais de uma vez.

## Decisão

- classificar deterministicamente cada PDF como `regular`,
  `thirteenth_advance` ou `thirteenth_final` a partir do cabeçalho E-TCM;
- rejeitar publicação automática quando o cabeçalho for desconhecido ou
  misturar ciclos incompatíveis;
- versionar e preservar cada componente separadamente;
- somar por código proventos, descontos e valores líquidos dos componentes
  vigentes para produzir o total mensal;
- usar somente a folha regular para a quantidade de vínculos;
- exigir exatamente uma folha regular e no máximo um componente de cada ciclo
  para publicar a projeção mensal;
- mostrar no portal todos os PDFs, hashes, datas de coleta e tipos de componente
  usados no total;
- manter temporariamente a leitura da projeção anterior durante a implantação,
  para que a página não desapareça entre o deploy da aplicação e a migration.

## Consequências

O mês passa a representar o custo documentado pela soma dos processamentos
oficiais sem dupla contagem de vínculos. Um segundo PDF não é tratado como
retificação sem evidência. Relatórios de terceirizados e estagiários permanecem
fora desta projeção até receberem classificação documental própria; sua ausência
no total será documentada, nunca convertida em zero.
