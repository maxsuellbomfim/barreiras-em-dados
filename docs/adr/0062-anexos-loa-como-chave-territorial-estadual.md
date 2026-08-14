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
