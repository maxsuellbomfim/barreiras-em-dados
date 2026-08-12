# Etapa 5 — descoberta da API Gestão de Parcerias do Transferegov

Data da observação: **12/08/2026**.

## Fonte e recorte

- publicação: Ministério da Gestão e da Inovação em Serviços Públicos;
- documentação: `https://api-publica.transferegov.gestao.gov.br/parcerias/docs`;
- OpenAPI: `https://api-publica.transferegov.gestao.gov.br/parcerias/openapi.json`;
- filtro territorial primário: `cd_ibge_recebedor=2903201`;
- CNPJ da Prefeitura usado somente como identificador complementar:
  `13654405000195`;
- o recebedor observado nas três propostas é o Fundo Municipal de Saúde de
  Barreiras, CNPJ `08595187000125`.

A API é nova e substitui gradualmente produtos anteriores do Transferegov.
O contrato deve ser monitorado e versionado; respostas brutas nunca serão
substituídas silenciosamente quando a fonte mudar.

## Resultado oficial observado

`GET /proposta?cd_ibge_recebedor=2903201` retornou três propostas de 2025:

| Proposta | Objeto | Situação informada | Valor de planejamento |
|---|---|---|---:|
| `9274` | incremento de média e alta complexidade | Aprovada | R$ 250.000,00 |
| `30854` | incremento de média e alta complexidade | Aprovada | R$ 5.000.000,00 |
| `31489` | incremento do piso da atenção primária | Aprovada | R$ 2.000.000,00 |

Esses valores são de planejamento da proposta. Não significam, sozinhos,
dinheiro pago nem execução do objeto.

### Encadeamento confirmado para a proposta `30854`

- distribuição: emenda de comissão `2025.5041.0002`, R$ 5.000.000,00;
- autoria publicada: `COMISSÃO DA SAÚDE`;
- parceria: `202500030009`, situação `Aprovada`;
- empenho: `2025NE493599`, R$ 5.000.000,00, emitido em 13/10/2025;
- documento hábil: `2025TF860130`, R$ 5.000.000,00;
- ordem de pagamento: `2025OP053944`, situação `Paga`;
- ordem bancária: `2025OB055607`, emitida em 24/10/2025.

### Encadeamento confirmado para a proposta `31489`

- distribuição: emenda de comissão `2025.5041.0001`, R$ 2.000.000,00;
- autoria publicada: `COMISSÃO DA SAÚDE`;
- parceria: `202500030643`, situação `Aprovada`;
- empenho: `2025NE494627`, R$ 2.000.000,00, emitido em 16/10/2025;
- documento hábil: `2025TF865057`, R$ 2.000.000,00;
- ordem de pagamento: `2025OP058301`, situação `Paga`;
- ordem bancária: `2025OB059959`, emitida em 30/10/2025.

Os textos das ordens citam pessoas como `solicitante`. Isso não autoriza
tratá-las como autoras da emenda. `autor`, `solicitante`, `comissão`,
`beneficiário` e `recebedor` serão papéis diferentes no modelo.

Para a proposta `9274`, a consulta observada não retornou empenho, documento
hábil ou ordem de pagamento. A ausência nesses endpoints na data da coleta
não é valor zero, cancelamento nem prova de que nenhum pagamento exista em
outra fonte.

## Decisões do primeiro conector

- preservar propostas, distribuições e parcerias como recursos separados;
- aceitar somente HTTPS no host oficial;
- limitar tamanho, tempo e paginação;
- preservar inclusive página vazia como evidência de cobertura;
- rejeitar item que não corresponda ao IBGE ou ao identificador pai pedido;
- não calcular totais, saldos ou estágios no coletor;
- não publicar antes de preservar a cadeia completa e validar os valores com
  `Decimal` na normalização.

## Persistência bruta implementada

Propostas, distribuições e parcerias passam a ser preservadas no bucket
privado por hash, com leitura de volta antes da gravação no banco. Cada item
recebe tipo, chave da fonte, versão do parser e idempotência próprios. A
execução e a cobertura são abertas antes da autenticação e da primeira
requisição; falhas entram no controle central, sem se tornarem página vazia.

O job permanece no grupo **Finanças** e reutiliza a identidade técnica já
provisionada, mas somente dentro do corredor
`transferegov/parcerias/`. Os schemas `source` e `raw` não recebem leitura de
`anon` ou `authenticated`.

## Limites e próxima fatia

Esta fatia ainda não cria projeção pública nem calcula valores. A próxima
fatia acrescentará empenhos, documentos hábeis, ordens de pagamento e ordens
bancárias, mantendo cada estágio independente. Somente depois será criada a
normalização com `Decimal`, reconciliação e linguagem acessível.

Transferências especiais são outro módulo. A varredura completa dos 410
beneficiários da Bahia não encontrou o CNPJ municipal de Barreiras em
12/08/2026; isso será registrado como observação da fonte, não como conclusão
de inexistência histórica de emendas ou transferências.
