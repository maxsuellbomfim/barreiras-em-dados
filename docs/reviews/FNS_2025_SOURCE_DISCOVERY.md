# FNS: piloto documental de Barreiras em 2025

## Resultado observado

Consulta em 05/09/2026 UTC. O detalhe oficial do FNS acrescenta o papel de
**solicitante** a dois pagamentos já presentes na série documental da CGU.
Não acrescenta R$ 7 milhões ao total existente e não muda autoria coletiva
para individual. O piloto não modificou banco, coletores, cron ou interface.

| Pagamento CGU já publicado | Data | Valor pago | Emenda CGU | Autor publicado pela CGU | Solicitante informado pelo FNS |
| --- | --- | ---: | --- | --- | --- |
| `257001000012025OB055607` | 24/10/2025 | R$ 5.000.000,00 | `202550410002` | COM. DA SAUDE | `4438` — NETO CARLETTO |
| `257001000012025OB059959` | 30/10/2025 | R$ 2.000.000,00 | `202550410001` | COM. DA SAUDE | `4125` — PEDRO LUCAS FERNANDES |

Os nomes e códigos acima são papéis expressamente informados na observação
oficial, não inferidos de similaridade textual. Os códigos de solicitante são
identificadores observados no FNS: não foram presumidos como IDs da Câmara ou
do TSE. Nenhum vínculo de perfil ou crédito de ranking foi criado.

Beneficiário consultado: Fundo Municipal de Saúde de Barreiras, CNPJ
institucional `08.595.187/0001-25`, esfera municipal, BA. O FNS usa código
territorial `290320`; o vínculo com IBGE `2903201` deve ser explícito.

## Evidência de ligação e limite de identidade documental

A ação `65061` informa processo `25000.184333/2025-70`, proposta
`36000703585202500`, portaria `8384`, OB `055607`, data de criação SIAFI
24/10/2025 e líquido R$ 5.000.000,00. A observação da OB repete a proposta,
identifica emenda `50410002`, Comissão da Saúde e solicitante `4438`.

A ação `68909` informa processo `25000.186806/2025-73`, proposta
`36000703903202500`, portaria `8411`, OB `059959`, data de criação SIAFI
30/10/2025 e líquido R$ 2.000.000,00. A observação da OB repete a proposta,
identifica emenda `50410001`, Comissão da Saúde e solicitante `4125`.

Nos dois detalhes: bruto igual ao líquido, descontos e anulações iguais a
zero, motivo de rejeição vazio. As duas respostas de OB confirmam
`municipio=BARREIRAS`, `codigoIBGE=290320`, `uf=BA`.

Uma consulta viva à projeção pública da CGU encontrou duas linhas neste
recorte, sem truncamento, com ano, emenda, data, valor e município compatíveis.
O FNS observado fornece número curto da OB, não a UG/gestão que integra a
chave completa da CGU. Portanto, a corroboração das duas amostras não autoriza
um join genérico pelo sufixo da OB. Um futuro reconciliador deve exigir todas
as evidências comparáveis, unicidade nos dois lados e estado explícito de
ambiguidade; não inventar a UG/gestão nem inferir o ano da emenda apenas do
ano do pagamento, inclusive em restos a pagar.

## Cobertura do piloto

O catálogo de ações Fundo a Fundo de 2025 retornou 33 linhas em quatro páginas
(10, 10, 10 e 3): 28 ações com ID positivo e cinco grupos sem repasse, com
`id=0`. Estes últimos não são pagamentos nem duplicatas a eliminar apenas
pelo ID. As linhas reconciliaram os totais oficiais:

- bruto R$ 112.420.799,22;
- descontos R$ 69.428,00;
- líquido R$ 112.351.371,22.

Os totais incluem transferências que não são emendas. O piloto detalhou
somente as duas ações acima e não comprova cobertura documental completa do
ano, de outras modalidades ou do período desde 2021. A fonte também oferece
`tipoConsulta=3` (Outros Pagamentos), fora deste recorte.

## Fonte, acesso e preservação

Entrada: [consultas oficiais do FNS](https://portalfns.saude.gov.br/consultas/),
opção [Consulta Detalhada de Pagamento](https://consultafns.saude.gov.br/#/detalhada).
O cliente público observado é a versão `1.50.8`; as rotas abaixo foram
localizadas em seus controladores e serviços, não por varredura de endpoints.
Não foi localizada garantia de estabilidade da API ou SLA nesta investigação.

Base `https://consultafns.saude.gov.br/recursos/`:

- `municipios/uf/BA`: comprova o código local;
- `tipos-consulta/2025`: comprova a modalidade;
- `consulta-detalhada/entidades`: ano 2025, tipoConsulta 2, estado BA,
  municipio 290320, page 1, count 10;
- `consulta-detalhada/detalhe-acao`: filtros anteriores mais CNPJ institucional,
  páginas 1–4, count 10;
- `consulta-detalhada/detalhe-pagamento`: mesmos filtros e `acoes=65061` ou
  `68909`, page 1, count 25;
- `consulta-detalhada/detalhe-ordem-bancaria`: anoPagamento 2025, mes 10,
  ano 2025, competencia `Única em 2025`, uf BA, numeroDocumentoSiafi `055607`
  ou `059959`, tipoDocumentoPagamento OB, page 1, count 10.

Cada um dos dois detalhes de pagamento e das duas OBs retornou total 1 e
totalPaginas 1. A API usa metadados de página inconsistentes entre recursos:
ações começaram em 1; entidades e pagamentos reportaram 0 para `page=1`.
Não presumir uma convenção única para todos os endpoints.

Após autorização do usuário, os três novos brutos foram guardados localmente
com DPAPI `CurrentUser`. A reabertura cifrada reproduziu tamanho e SHA-256 do
conteúdo recebido em todos os três casos. O primeiro pagamento já havia sido
preservado em pasta local não versionada na etapa anterior. Nenhum bruto,
agência, conta, credencial ou CPF pessoal integra este commit.

| Evidência | Bytes originais | SHA-256 do conteúdo original |
| --- | ---: | --- |
| Pagamento FNS `65061` — etapa anterior | 1.155 | `e34e60ee9e47bb80b9dc6db1096bbda2ebf8b0b777571f2a198b5306eac137bb` |
| OB FNS `055607` | 447 | `0845fe5d0b0c0a5fbbba34f912ca1366201c1089fe4204bd0570a858a2831fed` |
| Pagamento FNS `68909` | 1.100 | `08a32e45f12f8a7c4b380510bc7de0481f472f2f4802431430ce0818a71a39c0` |
| OB FNS `059959` | 455 | `184d38ddb7419cd4d15f930d28931480fe020e87666414acc10f2a332895c8b3` |

Arquivo CGU: [documentos de emendas de 2025](https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/2025_EmendasParlamentaresPorDocumento.zip),
hash preservado `3023ae72864f670962507c4500452eec2bca1d827482c995b1e06f5e2730c300`.

Consulta reproduzível na projeção pública, sem conteúdo bancário:

```sql
begin read only;
with s as (
  select * from api.get_public_cgu_federal_amendment_document_study(
    50, 0, 2025::smallint, null, 'payment', 'FUNDO MUNICIPAL DE SAUDE'
  )
)
select s.total_count, d->>'amendment_code' amendment_code,
  d->>'author_name' author_name, d->>'author_kind' author_kind,
  d->>'document_code' document_code, d->>'document_date' document_date,
  d->>'paid_amount' paid_amount, d->>'artifact_sha256' artifact_sha256
from s cross join lateral jsonb_array_elements(s.items) d;
commit;
```

## Próxima entrega proposta

1. Parser/conector FNS substituível, usando transporte, limites, retries e
   preservação existentes; sem cron nacional e sem nova dependência.
2. Projeção minimizada: município, entidade institucional, proposta, processo,
   portaria, data, tipo/número de documento, bruto/desconto/líquido/anulação,
   autor e solicitante em campos separados, com evidência/versionamento.
3. Testes antes da implementação: paginação repetida/alterada, grupos `id=0`,
   município errado, campo ausente versus zero, anulação, centavos, observação
   fora do formato, solicitante ausente/múltiplo e conflito de chave.
4. Primeiro uso público: explicar participação como “Solicitante informado
   pelo FNS”, sem somar o pagamento outra vez e sem alterar o autor coletivo.
   Não derivar cargo, legislatura, mérito ou execução física apenas do nome.

O valor do piloto é a evidência adicional de participação e a reconciliação;
não a promessa de novos recursos nem uma mudança de ranking sem metodologia.
