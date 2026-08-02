# Etapa 6A — primeiro recorte público do Executivo

## O que foi entregue

- a página de representantes passa a consultar a projeção pública de atos
  aprovados do Diário Oficial;
- nome, cargo, órgão, tipo do ato, trecho de sustentação, data, documento e
  hash aparecem juntos quando a fonte fornece esses campos;
- a lista é limitada aos atos aprovados e mostra no máximo 24 cartões na
  página de representantes; o histórico completo continua em `/atos`;
- a projeção é um recorte de atos publicados, não um cadastro completo do
  prefeito, vice-prefeito ou secretariado.

## Regra determinística

Para cada combinação normalizada de pessoa e cargo, o sistema conserva o ato
mais recente pelo campo de data do ato; quando a edição não informa a data, usa
a data da aprovação editorial como ordenação de fallback. A normalização remove
acentos, uniformiza caixa e espaços e não é usada para afirmar identidade entre
pessoas diferentes.

Uma exoneração continua sendo exibida como exoneração. Ela não é convertida em
"cargo atual" nem em conclusão reputacional.

## Correção de disponibilidade pública

O cliente web estava aceitando `approved-gazette-acts/1.6.0`, enquanto a
projeção SQL append-only vigente retorna `approved-gazette-acts/1.5.0`. Como o
cliente falha fechado diante de versão inesperada, atos aprovados podiam parecer
ausentes no site mesmo estando publicados no banco. O cliente foi alinhado à
versão efetivamente projetada.

## Fora desta fatia

- não há inferência de prefeito, vice ou secretário sem ato correspondente;
- remuneração, folha e subsídio exigem fontes contábeis próprias e não são
  derivados de nomeações;
- não há avaliação de desempenho, ranking ou conclusão sobre pessoas.

## Validação

- build e typecheck do portal web;
- testes do monorepo;
- validação da migration fundamental;
- `git diff --check`.
