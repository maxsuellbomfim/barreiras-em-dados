# Etapa 3 — contrato inicial de normalização da receita

## Escopo

Foi criado um normalizador puro para páginas do recurso oficial
`pdc-resumo-execucao-da-receita`. Ele recebe a resposta bruta já preservada e
produz objetos tipados para a próxima camada de persistência.

## Regras

- `resource`, `count` e `data` precisam corresponder ao envelope observado;
- `id`, `ano`, `descricao` e `valor_arrecadado` são obrigatórios;
- ano fiscal aceita somente quatro dígitos entre 1900 e 2200;
- datas seguem ISO `YYYY-MM-DD`;
- valores usam `Decimal`, nunca `float`, e aceitam a notação brasileira
  `1.234,56`;
- valores negativos, ambíguos ou com separador incompatível são rejeitados;
- nenhum campo ausente é preenchido por inferência;
- a etapa não soma registros, não escolhe uma fonte vencedora e não publica
  totais.

## Próxima etapa necessária

Antes de gravar em `finance.revenues`, ainda é preciso confirmar no ambiente
real os campos de classificação, unidade, estorno/retificação, chave estável e
órgão responsável. A fixture atual é sanitizada e contém apenas valores zero.

## Validação

- quatro testes unitários do normalizador;
- Ruff no novo pacote e nos testes;
- fixture sanitizada da fonte oficial como contrato de entrada.

