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

## Próximo passo

Sonda de coletor em `workers/collectors`: abrir sessão, fixar o período por
mês e preservar a resposta bruta (ou o export oficial, se o formato for
estável), começando por empenhos de um mês fechado.
