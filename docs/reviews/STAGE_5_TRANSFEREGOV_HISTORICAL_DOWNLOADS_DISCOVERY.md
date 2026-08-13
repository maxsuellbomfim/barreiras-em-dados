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

## Validação do arquivo de propostas em 12/08/2026

O endereço operacional do arquivo é o proxy oficial
`https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_proposta.zip`.
A URL do blob declarada no catálogo é preservada como proveniência, mas não é
usada diretamente para download porque respondeu com acesso negado no ensaio.

O arquivo observado tinha:

- 205.017.763 bytes compactados;
- SHA-256 `5947f8ef1457b29e938e017dfb7a05076b0c5301c21296d4eefef1ac44700989`;
- ETag `0x8DEF8636FB12944`;
- membro único `siconv_proposta.csv` com 36 colunas;
- 1.155.782 linhas nacionais;
- 199 propostas com `COD_MUNIC_IBGE=2903201` entre 2008 e 2026;
- 69 propostas no recorte inicial de 2021 a 2026.

Esses números descrevem somente a versão observada e não são codificados como
totais permanentes. Cada execução confere novamente tamanho, ETag, schema,
integridade ZIP, código IBGE e período antes de fechar a cobertura.

## Decisões desta fatia

- cadastrar `transferegov-downloads` separadamente de
  `transferegov-parcerias`;
- preservar o XML integral antes de materializar entradas;
- aceitar somente HTTPS e o host/contêiner oficiais;
- exigir todos os oito arquivos e `NextMarker` vazio para cobertura completa;
- guardar somente cabeçalhos HTTP em allowlist;
- registrar execução antes da autenticação e da primeira requisição;
- baixar o ZIP somente por acionamento manual explícito na primeira validação;
- manter o ZIP nacional integral no armazenamento privado e fragmentá-lo pelo
  mecanismo imutável já existente quando ultrapassar o limite do objeto;
- excluir da projeção normalizada agência, conta bancária, CEP, endereço e
  bairro do proponente;
- rejeitar identificador de proponente com formato de CPF no recorte municipal;
- não calcular, agregar ou publicar valores nesta fatia.

## Próxima menor fatia

Executar o coletor controlado em produção e conferir o artefato, os 69 registros
esperados para a versão observada e a partição anual. Depois, processar
`siconv_emenda.zip` para ligar número, autoria e valor às propostas sem somar
estágios nem atribuir autoria por mera semelhança de nome.

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
