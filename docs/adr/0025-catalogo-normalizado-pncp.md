# ADR 0025 — Catálogo normalizado de opções PNCP

## Status

Aceito — primeira versão.

## Decisão

O catálogo de sugestões de compras agrupa valores de modalidade, situação e
órgão por uma chave determinística que reduz espaços repetidos, ignora caixa e
remove diferenças de acentuação. O texto original mais representativo continua
exibido e todas as variantes observadas são preservadas na resposta.

O agrupamento serve para descoberta e navegação. Ele não altera o registro
bruto, não corrige a fonte e não cria uma conclusão sobre o órgão ou fornecedor.

## Limitações

- A normalização não resolve abreviações semanticamente diferentes.
- A variante exibida é a menor em ordem lexicográfica; o conjunto completo fica
  disponível para auditoria.
- O filtro estruturado ainda compara o texto publicado; o uso da chave
  normalizada na filtragem será uma etapa posterior, após testes com variações
  reais.

## Próxima etapa

Aplicar a chave normalizada aos filtros e iniciar o vínculo determinístico entre
contratações PNCP, contratos, empenhos e pagamentos preservados.
