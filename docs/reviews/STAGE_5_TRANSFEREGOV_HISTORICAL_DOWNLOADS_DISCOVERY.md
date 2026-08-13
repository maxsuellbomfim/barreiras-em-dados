# Etapa 5 — catálogo histórico do Transferegov

Data da observação: **12/08/2026**.

## Problema de cobertura

A API atual de Gestão de Parcerias devolve três propostas destinadas a
Barreiras, todas de 2025. Consultas anuais de 2021 a 2026 confirmam esse retrato
somente para a API nova. Elas não provam que o Município não recebeu recursos
em anos anteriores.

O MGI também publica arquivos nacionais de transferências discricionárias e
legais. A área oficial informa que esse módulo ainda está em migração gradual
para as APIs novas. Logo, o backfill histórico precisa consumir os downloads,
não repetir indefinidamente a API atual.

## Catálogo observado

- página oficial: `https://api-publica.transferegov.gestao.gov.br/downloads`;
- enumeração: `https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/?restype=container&comp=list`;
- formato: XML de enumeração de blobs;
- contêiner declarado: `trsfgov-prod-public-data`;
- host declarado: `trsfgovprodstrgaccpublic.blob.core.windows.net`;
- metadados disponíveis: nome, URL, tamanho, modificação, ETag, tipo e MD5
  quando a fonte o publica.

Conjuntos selecionados no primeiro contrato:

| Arquivo | Papel inicial | Tamanho observado |
|---|---|---:|
| `siconv_proposta.zip` | localizar propostas ligadas ao Município | 195,52 MiB |
| `siconv_proponentes.zip` | confirmar identidade do proponente | 6,06 MiB |
| `siconv_convenio.zip` | instrumento celebrado e situação | 17,48 MiB |
| `siconv_emenda.zip` | número, autoria e valor da emenda | 7,92 MiB |
| `siconv_empenho.zip` | estágio de empenho | 21,92 MiB |
| `siconv_desembolso.zip` | eventos de desembolso | 15,82 MiB |
| `siconv_pagamento.zip` | pagamentos associados | 348,87 MiB |
| `siconv_termo_aditivo.zip` | alterações do instrumento | 57,40 MiB |

Tamanhos são metadados do retrato observado e podem mudar. Eles não devem
ser codificados como limite ou expectativa permanente.

## Decisões desta fatia

- cadastrar `transferegov-downloads` separadamente de
  `transferegov-parcerias`;
- preservar o XML integral antes de materializar entradas;
- aceitar somente HTTPS e o host/contêiner oficiais;
- exigir todos os oito arquivos e `NextMarker` vazio para cobertura completa;
- guardar somente cabeçalhos HTTP em allowlist;
- registrar execução antes da autenticação e da primeira requisição;
- não baixar ZIPs, calcular valores ou publicar linhas nesta fatia.

## Próxima menor fatia

Baixar `siconv_proposta.zip` em fluxo com limite, hash e validação ZIP/CSV;
descobrir seu schema por fixture; filtrar por código IBGE/CNPJ oficial de
Barreiras; preservar a evidência da versão do ZIP e as linhas municipais; e
comparar a cobertura encontrada com a API atual sem somar registros ainda.

## Validação de produção em 13/08/2026

A execução manual limitada
[`31658851731`](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31658851731)
confirmou o catálogo oficial com HTTP 200 e hash
`4d5cab986a19801f97e0b1a6a1fc864fb6bd50d60472aeb4c7db9a4c84e0d3da`,
mas o Storage recusou o artefato com `invalid_mime_type`: o bucket privado
`raw-artifacts` ainda não admitia `application/xml`.

A correção mantém o bucket privado e amplia somente a allowlist de MIME types.
O teste de migration exige explicitamente `application/xml`; o workflow deverá
ser repetido após a migration ser aplicada. Um HTTP 200 sem preservação do
artefato continua sendo falha, não cobertura completa.

A execução comparativa
[`31660063594`](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31660063594)
comprovou que upload e leitura de volta passaram após a correção do MIME. A
persistência relacional então expôs um segundo contrato: o repositório comum
exige `offset` e `size` no cursor de toda página. O catálogo fornecia somente
`selected_files` e falhou com `KeyError`, antes de gravar registros ou declarar
cobertura. A regressão agora fixa explicitamente os três campos do cursor.

A validação da branch corrigida
[`31660257114`](https://github.com/maxsuellbomfim/barreiras-em-dados/actions/runs/31660257114)
concluiu os dois jobs. A consulta direta posterior confirmou:

- execução `succeeded` e partição `complete`;
- artefato XML com 36.443 bytes e SHA-256
  `4d5cab986a19801f97e0b1a6a1fc864fb6bd50d60472aeb4c7db9a4c84e0d3da`;
- oito registros, um para cada arquivo contratado;
- `observed_records = 8` e nenhuma falha não resolvida.

Somente após essa prova a fatia do catálogo pode ser considerada operacional.
