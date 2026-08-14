# ADR 0066 — Ranking de emendas por legislatura e esfera

- Estado: aceita
- Data: 2026-08-14

## Contexto

Somar toda a série histórica em um único ranking mistura mandatos, Casas
legislativas e estágios financeiros diferentes. As fontes disponíveis informam
o exercício da emenda, mas não uma data individual confiável para todos os
registros. Em 2023, Câmara dos Deputados e ALBA iniciaram novas legislaturas em
fevereiro; portanto o ano civil atravessa duas legislaturas.

## Decisão

Publicar até dez autorias individuais por legislatura, separando esfera federal
e estadual. A classificação usa somente anos civis inteiros contidos no período
da legislatura. O exercício de 2023 fica explicitamente excluído até existir
data oficial individual suficiente para atribuição segura.

O ranking federal ordena pelo valor destinado a Barreiras na série reconciliada
do Transferegov. O ranking estadual ordena pelo valor autorizado nos anexos da
LOA da Bahia. Empenho, liquidação e pagamento ficam em colunas separadas e não
alteram a ordem.

Os períodos e suas fontes ficam na tabela privada
`political.legislative_terms`. A aplicação pública recebe apenas a projeção
`api.get_public_parliamentary_legislature_rankings`. A tabela usa RLS forçada e
não concede leitura a `anon` ou `authenticated`.

## Consequências

- evita atribuição falsa de registros de 2023;
- não mistura recursos estaduais e federais;
- não transforma “autorizado” ou “destinado” em “pago”;
- preserva autores sem perfil atual associado;
- permite adicionar novas legislaturas sem alterar a regra de cálculo;
- pode mostrar menos de dez nomes quando a cobertura oficial ainda for menor.

## Alternativas rejeitadas

- atribuir todo 2023 à legislatura nova: impreciso sem data individual;
- atribuir todo 2023 à legislatura antiga: impreciso pelo mesmo motivo;
- ordenar por pagamento: penalizaria registros cuja execução ainda não foi
  localizada e misturaria decisão parlamentar com execução administrativa;
- usar cargo atual para inferir a esfera histórica: produz retroatividade falsa.
