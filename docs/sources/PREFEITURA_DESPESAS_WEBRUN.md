# Despesas da Prefeitura no sistema Sudoeste (WebRun)

- Observado em: 23/09/2026 (somente leitura, navegador e GET simples)
- Publicador: Prefeitura Municipal de Barreiras, por sistema da Sudoeste
  Informática
- Porta de entrada: <https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral>
- Sistema: WebRun 5 (Maker/SmartClient), Tomcat 9, conexão `PM_Barreiras`

## Por que importa

É a primeira fonte observada com **empenho individual** do Município. A API
`/api?resource=` do portal não tem `empenhos`, `liquidacoes` nem `pagamentos`
(resposta "Recurso não encontrado ou não permitido."), e o TCM-BA entrega PDFs.
Sem esta fonte o gate 4 (rastro do dinheiro) não tem de onde partir.

## Formulários

| Estágio | formID |
| --- | --- |
| Empenhos | 7901 |
| Liquidações | 7907 |
| Pagamentos | 7910 |

```text
GET /webrun5/openform.do?sys=PTP&action=openform&formID=7901&dataConnection=PM_Barreiras&numerotc=39
```

`form.jsp` com os mesmos parâmetros só devolve a moldura; o conteúdo vem de
`openform.do`, com sessão (`JSESSIONID`) e token CSRF próprios do WebRun. Os
registros do período padrão chegam embutidos no HTML (~245 KB); filtros e
navegação passam por `POST /webrun5/executeRule.do` e
`GET /webrun5/navigate.do?...&componentID=1082469`. Há botão "Exportar Dados"
(não acionado: download não autorizado nesta observação). Sem `robots.txt`
(404).

## Campos observados em empenhos

Grade `DESPESAS`, 1.921 empenhos no período padrão (mês corrente, 01 a
23/09/2026); cabeçalho informa dados desde 06/01/2017 e série histórica
separada para anos anteriores a 2024.

- visíveis: data, tipo da nota (Estimativa, Global, Ordinária), órgão
  (Prefeitura, Fundo Municipal de Saúde...), nº do empenho (`2281/5`),
  subelemento, favorecido, valor, resto a pagar;
- ocultos no registro: identificador interno (`252163`, `O-252163`),
  códigos numéricos ainda sem semântica confirmada e **histórico** em texto
  livre.

## Ligação com contrato

O histórico cita o contrato literalmente em parte dos empenhos, por exemplo
"Concorrência Pública nº 001/2025, Contrato nº 070-FMS/2025 no valor de
1.882.260,12". Uma expressão simples encontrou número de contrato em ~300 dos
1.921 empenhos do mês. Três números conferidos existem em
`municipal_transparency_contratos` com o mesmo favorecido (`070-FMS/2025`,
`071-FMS/2025`, `260/2021`); no primeiro, o valor do contrato também coincide.

A chave é texto do próprio registro oficial, não inferência; mesmo assim a
ligação exige regra determinística versionada (número normalizado + órgão +
favorecido compatível) e ADR antes de publicar. Empenho sem citação fica sem
ligação, nunca ligado por valor ou nome parecido.

## Riscos

- favorecido pessoa física pode aparecer (diárias, prestadores): aplicar o
  mesmo corte de dados pessoais de `contratos` e `servidores`;
- o sistema é de terceiro, sem versionamento: preservar o HTML/export bruto
  por SHA-256 e falhar explicitamente quando a grade mudar;
- volume: ~2 mil empenhos/mês na Prefeitura; coletar por mês, em baixa
  frequência.

## Sonda (23/09/2026)

`barreiras_collectors.connectors.municipal_expenses` reproduz a consulta sem
navegador, em uma sessão:

1. `GET openform.do?...formID=7901` abre a sessão (cookie `JSESSIONID`);
2. `POST executeRule.do` com `ruleName=TRP_TRANSP_DESPESDA_MODIFICAR_CONSULTA`,
   `P_0`/`P_1` = primeiro e último dia do mês, `P_6=P` e os demais `P_0..P_24`
   vazios; a resposta declara `setTotalRows(N)`;
3. `GET navigate.do?...componentID=1082469&param=first&gt=0` devolve a grade
   inteira como JavaScript ISO-8859-1, sem paginação (`isLastPage = true`).

Não há token CSRF. A resposta é determinística: o mesmo mês baixado duas vezes
teve o mesmo SHA-256. Execução real (`probe_municipal_commitments --month`):

| Mês | Linhas | Repetidas | Únicas (O-/E-) | Citam contrato | Grade |
| --- | ---: | ---: | --- | ---: | ---: |
| 2026-08 | 2.313 | 117 | 1.804 / 392 | 555 | 21,9 MB |
| 2025-01 | 4.485 | 102 | 4.026 / 357 | 1.634 | 42,6 MB |
| 2023-12 | 1.921 | 44 | 1.877 / 0 | 848 | 18,4 MB |

Contrato observado e validado pela sonda:

- chave oficial `CHAVE`: `O-<n>` orçamentária, `E-<n>` extra-orçamentária
  (retenções de folha e similares, que não são despesa empenhada e precisam
  ficar fora de qualquer série de empenho);
- a fonte repete linhas inteiras; repetição idêntica é aceita e contada, mesma
  chave com conteúdo diferente é falha;
- nomes internos dos campos vêm na própria grade (`PES_NOME`,
  `EMP_HISTORICO`, `NUMERO_DESPESA`, `VALORCHAR`, `DOTACAO`, `EMP_COD`);
- total declarado diferente das linhas, grade paginada, linha fora do mês ou
  erro da regra (`interactionError`) são falhas explícitas.

**Série histórica:** com "Adicionar série histórica = Sim" (`P_2=S`), a fonte
responde `SQLException: Invalid column name 'NUMERO_DESPESA_2'` para qualquer
período. Sem ela, meses anteriores a 2024 vêm só em parte (15 empenhos em
03/2021, 59 em 06/2022, 1.921 em 12/2023); a sonda os marca como
`partial_source_history_unavailable`, nunca como completos.

**Volume:** ~20–45 MB por mês, dos quais a maior parte é o JavaScript do botão
de detalhe repetido por linha; o bruto precisa ser preservado mesmo assim.

## Próximo passo

Persistir cada mês fechado como `raw_artifact` (SHA-256) e um `raw_record` por
chave, com estado de cobertura; depois a ligação empenho→contrato pelo número
citado, preservando o sufixo do órgão (`070/2025` e `070-FMS/2025` são
contratos distintos), com ADR antes de publicar. Liquidações (7907) e
pagamentos (7910) seguem o mesmo protocolo, ainda não sondado.
