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

### Leitor de evidência implementado em 05/09/2026

`barreiras_collectors.connectors.fns_payment_evidence.parse_fns_payment_evidence`
recebe os bytes preservados de um pagamento e de sua OB, mais o escopo
explícito (`action_id`, `payment_year`, `order_number`). Retorna somente os
campos permitidos e os dois SHA-256. Não faz requisições, não persiste, não
publica e não resolve identidade. O chamador deve obter o par na consulta
exata da entidade institucional; a resposta OB não identifica UG/gestão.

Limites deliberados do piloto:

- uma linha em cada resposta, sem páginas adicionais; vazio exige tratamento
  pelo futuro coletor, não significa sucesso deste leitor;
- pagamento municipal Fundo a Fundo, OB, Barreiras/BA, competência única,
  período consistente e valor líquido positivo reconciliado em centavos;
- anulações, rejeições, outros formatos de competência, múltiplos pagamentos
  e observações não reconhecidas ficam fora deste escopo e exigem revisão,
  **não são classificados como erros da fonte nem descartados**;
- o número de emenda de oito dígitos não informa seu ano: `amendment_year`
  permanece nulo; `link_status=unlinked` impede interpretar a leitura como
  associação já comprovada com pessoa ou documento CGU;
- `requester_source_code` é apenas código publicado pelo FNS, não ID da Câmara
  ou TSE. Ausência de solicitante permanece nula, sem usar o autor como substituto;
- bruto, desconto e líquido ficam separados. Nada é somado à base CGU;
- campos bancários, observação bruta e mensagens de erro da fonte não entram
  na saída. Não há fixture real com dados bancários no Git.

A API oficial reproduziu uma diferença de codificação no campo `competencia`
da OB: mesmo recebendo `%C3%9Anica%20em%202025`, devolve a representação UTF-8
interpretada como Latin-1. O leitor aceita somente essa variante exata de
`Única em <ano>`, sem corrigir nomes ou alterar os bytes preservados.
A consulta adicional da OB `055607` reproduziu o mesmo SHA-256 acima.

Validação com os arquivos oficiais preservados: ação `65061`/OB `055607`
resultou em R$ 5.000.000,00 e solicitante Neto Carletto; ação `68909`/OB
`059959` em R$ 2.000.000,00 e solicitante Pedro Lucas Fernandes. Em ambas,
o autor permaneceu Comissão da Saúde. Isso comprova a leitura desses dois
pares, **não cobertura nacional/histórica nem integração já publicada no site**.

### Reconciliação executada em 05/09/2026

`fns_cgu_reconciliation.reconcile_fns_cgu_payment` recebe os dois brutos FNS e
o ZIP anual completo da CGU. Reutiliza os leitores existentes e não aceita
uma lista paginada ou previamente filtrada como prova de unicidade.

O piloto restringe o beneficiário ao CNPJ institucional `08595187000125`,
publicado no seletor FNS e confirmado por consulta read-only aos dois registros
CGU. Primeiro localiza todas as linhas de pagamento para esse beneficiário,
município e sufixo anual/OB; só depois confere a linha única por data, valor,
código completo, UG `257001`, emenda e autoria coletiva observada. Uma segunda
linha, mesmo com outro valor ou outra gestão, bloqueia a associação. Repetições
literalmente idênticas seguem a deduplicação do leitor CGU existente.

O resultado diferencia `not_found`, `ambiguous`, `conflict` e `unique_candidate`.
Arquivo inválido gera erro separado, nunca `not_found`. A grafia do autor é
preservada separadamente em cada fonte; nenhum código FNS vira ID de pessoa.
O ano da emenda vem da CGU, não do ano do pagamento. A chave de reconciliação
inclui os três hashes e muda quando o arquivo anual muda.

Prova operacional: novo download integral do ZIP CGU 2025 conferiu o SHA-256
`3023ae72864f670962507c4500452eec2bca1d827482c995b1e06f5e2730c300`
já preservado no projeto. O reconciliador retornou um candidato em cada par:

| Documento CGU | Linha no CSV | Solicitante FNS | Chave de reconciliação |
|---|---:|---|---|
| `257001000012025OB055607` | 281848 | Neto Carletto | `12f0a9c778c4554cbc254f6bf8613abef0ac3b3e64edd481120468ae3e377789` |
| `257001000012025OB059959` | 321164 | Pedro Lucas Fernandes | `a52c1d1312249eb6240d63dfefc6af4b1a72ffef7422e29243f9ee46f987d53f` |

`publication_allowed` continua falso: candidato único não equivale a decisão
de publicação. Não foi escrita linha financeira ou de identidade no banco.
A carga real da evidência/decisão e sua exibição pública permanecem pendentes.

### Registro versionado da evidência e da revisão

A migration `20260905040239_fns_cgu_evidence_registry.sql` cria
`source.fns_cgu_evidence` e `source.fns_cgu_decisions`, sem leitura ou escrita
pelos papéis comuns da aplicação. Evidências referenciam os três originais
registrados e a linha CGU; decisões são acrescentadas, nunca sobrescritas.
O trigger confere metadados oficiais, hashes e os campos do registro bruto CGU.
Isso não substitui conferir os bytes no Storage e executar os leitores novamente.

`api.get_public_fns_cgu_links` aceita até 50 códigos e devolve somente documento,
solicitante, autor FNS, hashes, fonte, data da revisão e versão metodológica.
Só retorna a última versão aprovada e compatível com a linha CGU atual, sem
duplicidade. Arquivo CGU alterado, nova evidência pendente ou revogação suspendem
a projeção. Não retorna campos bancários, IDs privados, notas ou valores, nem
escreve em registros financeiros ou de identidade.

Quatro testes executam a migration em PostgreSQL embarcado (PGlite), cobrindo
aprovação/revogação, invalidação, divergências, imutabilidade, permissões e limite
da API. As fixtures são sintéticas. A migration e o contrato estão implementados;
nenhum dos dois pares reais foi importado por esta entrega. A aplicação remota,
o upload privado, a leitura/hash de retorno e a revisão operacional ainda devem
ser comprovados antes de usar o vínculo na interface.

### Entregas restantes

Atualização operacional de 05/09: a migration do registro versionado já está
aplicada no Supabase. Consulta read-only encontrou zero evidências, decisões
e artefatos FNS. A fonte ainda não estava cadastrada. A migration
`20260905111757_register_fns_payment_source.sql` corrige essa precondição com
as rotas `payment-detail` e `payment-order-detail`, para uso manual no piloto.
O limite de seis requisições/minuto é uma política local conservadora, não
uma cota oficial anunciada pelo FNS. Reaplicação não duplica nem reativa rotas
pausadas. O cadastro não concede acesso ao Storage, não inicia download, não
registra cobertura e não aprova vínculo. A carga dos originais continua pendente.

1. Conector FNS substituível, usando transporte, limites, retries e
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
