# ADR 0060 — reconciliação das séries federais de emendas

## Contexto

O Transferegov oferece uma API corrente e arquivos históricos. As duas séries
podem conter a mesma emenda e não têm a mesma cobertura temporal. Somá-las sem
reconciliação duplicaria valores; escolher uma fonte como vencedora apagaria
evidências e diferenças úteis para auditoria.

## Decisão

O Barreiras 360 reconcilia as séries somente pela combinação exata do
identificador da proposta com o número oficial da emenda. Uma correspondência
também exige igualdade de ano, autoria normalizada, tipo de autoria e valor
destinado.

- correspondências exatas formam uma única linha pública;
- registros presentes em apenas uma série continuam publicáveis com essa
  condição explícita;
- chaves repetidas ou divergências entre fontes permanecem visíveis como
  conflito e não entram em totais nem rankings;
- empenho e pagamento continuam provenientes da série corrente, quando a
  atribuição financeira é determinística;
- URLs e hashes das duas fontes são preservados separadamente;
- perfis políticos só são ligados pelo crosswalk oficial já revisado.

## Consequências

O ranking consolidado mede valores destinados encontrados nas fontes, não
qualidade do mandato nem execução do objeto. A cobertura pode crescer sem
recontar emendas já vistas. Conflitos exigem correção de fonte, parser ou revisão
antes de qualquer valor entrar no total.
