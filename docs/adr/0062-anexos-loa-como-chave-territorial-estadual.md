# ADR 0062 - Anexos da LOA como chave territorial estadual

- Estado: aceito
- Data: 13/08/2026

## Contexto

O ZIP diario de emendas estaduais preservado pelo Barreiras 360 informa autor,
dotacao, empenho, liquidacao e pagamento, mas nao publica municipio. A SEPLAN-BA
mantem, nos anexos da Lei Orcamentaria Anual, demonstrativos oficiais de emendas
individuais por municipio e autor. Esses documentos fornecem a chave territorial
que faltava, mas registram autorizacao orcamentaria, nao execucao financeira.

O link rotulado no catalogo oficial como Anexo III da LOA 2021 resolve para um
arquivo cujo nome e conteudo correspondem a 2020. Consumir esse arquivo como
2021 produziria uma cobertura historica falsa.

## Decisao

Preservar os PDFs oficiais de 2022 a 2026 em corredor privado e imutavel,
separado do ZIP de execucao. Cada ano recebe sua propria particao, URL exata,
SHA-256, tamanho, anexo e estagio `authorized`. O ano de 2021 e registrado como
`blocked`, com o defeito da fonte descrito, e nenhum download do documento de
2020 e realizado em seu lugar.

O coletor grava somente o PDF e um manifesto tecnico. Extracao de autores,
municipios e valores pertence a `workers/document-processing`; normalizacao e
reconciliacao com execucao pertencem aos workers correspondentes.

A extracao usa duas gramaticas versionadas: linhas agrupadas por municipio em
2022-2025 e linhas agrupadas por autor em 2026. O campo territorial precisa ser
literalmente `Barreiras`; uma mencao da cidade no objeto nao qualifica a linha.
O valor e persistido como decimal e sempre recebe o estagio `authorized`. Hash
divergente, pagina sem texto, zero linhas territoriais, autor ausente em 2026 ou
duplicidade de autor e numero falham de forma auditavel. Nenhum desses casos e
publicado como zero.

## Consequencias

- Barreiras pode ser localizado por uma coluna/agrupamento territorial oficial;
- valor constante da LOA nao pode ser chamado de pago, recebido ou executado;
- ranking futuro devera separar autorizado, empenhado, liquidado e pago;
- ausencia de linha sera descrita como nao encontrada na fonte consultada, nunca
  convertida silenciosamente em zero;
- 2021 permanece observavel como bloqueio de qualidade da fonte.
- as linhas extraidas permanecem internas ate a conferencia do primeiro replay
  e a criacao de uma projecao publica separada dos valores executados.

## Adendo de 14/08/2026 - unicidade no universo estadual

A chave territorial de Barreiras prova onde a autorização foi destinada, mas
não prova que a combinação autor, órgão, unidade e ação seja exclusiva no
arquivo de execução. Para o Anexo I de 2026, o processador passa a indexar
privadamente todas as linhas estruturadas do documento, sem normalizar nem
publicar município ou valor de outros territórios.

A reconciliação com empenho, liquidação e pagamento deverá exigir unicidade
bidirecional: uma ocorrência da chave no anexo estadual inteiro e uma
ocorrência no retrato de execução. Qualquer colisão mantém o estágio financeiro
bloqueado e preserva as evidências das duas fontes para diagnóstico.

O replay de 14/08/2026 confirmou a necessidade desse gate. Das 27 autorizações
de Barreiras em 2026, 9 possuem chave única nos dois lados, 17 colidem no anexo
estadual e 1 não foi encontrada no retrato de execução. A decisão passa a ser
materializada em uma view privada: somente os 9 pares únicos carregam valores e
evidência de execução; os outros 18 retornam valores nulos e um motivo de
bloqueio. Nenhum valor executado é publicado por este primeiro adendo.

## Adendo de 14/08/2026 - projeção pública com cobertura explícita

Os nove pares bidirecionalmente únicos passam a ser elegíveis à projeção
pública de empenho, liquidação e pagamento. Os outros 18 registros continuam
públicos como autorizações da LOA, mas sem valores de execução e com o motivo
determinístico do bloqueio.

A API fornece separadamente o total autorizado de todas as 27 emendas e os
totais financeiros apenas do subconjunto conciliado. A página deve explicar os
dois universos e não poderá construir ranking de pagamento com cobertura
parcial. Valor zero é aceito somente quando consta na fonte de execução de um
par confirmado; campo ausente ou ligação bloqueada permanece nulo.

## Adendo de 14/08/2026 - snapshot para leitura pública

A view de reconciliação permanece como cálculo privado e fonte canônica, mas
não é mais executada durante requisições públicas. O plano medido em produção
reprocessava milhares de linhas JSON e excedia o timeout do PostgREST, embora o
resultado final tivesse somente dezenas de registros.

Uma tabela privada materializa o resultado validado. A atualização ocorre em
uma única transação ao fim do processamento da LOA, inclusive quando não há
novo anexo pendente, para incorporar um retrato de execução mais recente. As
APIs leem exclusivamente esse snapshot indexado. A role pública não pode ler a
tabela nem executar a rotina de atualização; somente o worker recebe esse
privilégio. Cada refresh registra contagem e versão metodológica na auditoria.

## Adendo de 03/09/2026 - execução agregada de grupos exclusivamente territoriais

Uma chave repetida no anexo continua impedindo atribuir execução a uma emenda
individual. Entretanto, quando todas as ocorrências estaduais dessa chave são
emendas destinadas a Barreiras e existe exatamente uma linha de execução, o
valor da execução pode ser publicado para o grupo completo.

A projeção de grupo mantém a lista de números das emendas e a soma autorizada
separadas da dotação, do empenho, da liquidação e do pagamento agregados pela
fonte estadual. Nenhum desses estágios é repartido entre as emendas, incorporado
ao ranking individual ou somado aos pares já conciliados. Chaves que também
incluam outro município permanecem bloqueadas por inteiro.
