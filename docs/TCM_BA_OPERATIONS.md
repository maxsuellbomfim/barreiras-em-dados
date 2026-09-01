# Operação do catálogo mensal do TCM-BA

## Seleção documental exata por categoria

Uma recuperação dirigida pode informar, no workflow **Coletar documentos
mensais do TCM-BA**, uma competência explícita e o código oficial da categoria.
Para o demonstrativo analítico de despesa, use `PCMGE015`. O código é validado
antes de acessar a fonte e não pode ser usado sem competência; se a categoria
não existir entre os documentos pendentes, a execução é bloqueada.

O diagnóstico local de linhagem também pode conferir a origem de um PDF já
preservado sem ler seu conteúdo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-document-pilot.ps1 `
  -DocumentLineageOnly `
  -ArtifactSha256 <sha256>
```

Em 01/09/2026, esse diagnóstico associou o hash
`efbebf2fb048c37e5ea5e7052282281cfcb043b4a69d3237d68a10757e02081d`
exclusivamente à competência `01/2021`, categoria `PCMGE015`. Portanto, ele não
fecha a lacuna municipal de abril de 2023.

Na mesma data, a recuperação exata de `PCMGE015` em `04/2023` preservou o PDF
`6670a953af416ee2d9028653ffe2b67f1c8e047cdc9d31b94fa13ed8e63620fe`.
A auditoria física releu o PDF e o XML de preparação, verificou 993.957 bytes,
dois hashes distintos, um vínculo exato com o catálogo e nenhuma falha aberta.
O processamento dirigido pelo mesmo SHA registrou 184 páginas, todas com
texto embutido e nenhuma aguardando OCR. A competência continua `partial`, com
1 de 1.824 documentos preservados; esta recuperação não declara o mês completo.

O parser determinístico específico do SIGA também foi validado em memória
sobre as 184 páginas desse PDF. Ele reconheceu 2.655 linhas analíticas e 25
unidades orçamentárias e exigiu igualdade entre cada linha, os subtotais das
unidades, o `Total do Poder` e os valores repetidos no resumo. O benchmark
fechou sem conflito e confirmou, para abril de 2023, R$ 16.029.966,95
empenhados no mês, R$ 62.639.688,25 liquidados e R$ 56.656.735,88 pagos. Esses
valores ainda não são publicados por este estágio. A migration de linhagem
financeira passa a aceitar somente a cadeia oficial `PCMGE015` -> preparação
-> PDF e o publicador dirigido pode selecionar o artefato por SHA-256. Ele
reconcilia as 2.655 linhas, mas persiste somente os totais: descrições com
caracteres de substituição permanecem indisponíveis em vez de serem exibidas de
forma enganosa. A publicação operacional exige migration aplicada, replay do
hash exato e auditoria posterior do RPC público.

Quando `-CategoryCode` é usado, o wrapper exige exatamente um hash retornado
pelo coletor e encaminha esse hash tanto ao processador de texto quanto ao
inventário de família. Ele encerra o caminho dirigido antes dos processadores
globais de contratos e empenhos. Para retomar apenas o texto de um PDF já
preservado, sem nova coleta nem consumo de outra fila, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-document-pilot.ps1 `
  -DocumentTextOnly `
  -ArtifactSha256 <sha256>
```

## Escopo e limite

O comando cataloga as prestações mensais e os documentos entregues pela
Prefeitura de Barreiras no e-TCM. Ele preserva cada resposta HTML e só fecha a
competência quando a contagem integral confere. Esta etapa não baixa os PDFs,
não extrai valores e não cria projeção pública financeira.

## Restrição de rede observada

Em 24/08/2026, o endpoint oficial respondeu pelo acesso residencial usado na
validação, mas expirou quatro vezes antes da página inicial a partir de um
runner hospedado pelo GitHub. A execução `32750879301` foi registrada como
falha; a competência não recebeu cobertura `complete`.

Não trate esse evento como competência vazia. Enquanto o TCM-BA não responder
de forma estável a datacenters, use o executor local pelo IP autorizado. Não
adicione proxy informal, serviço de bypass ou espelho não oficial.

## Execução local segura

O arquivo ignorado `.env.collector.local` deve conter somente:

```dotenv
COLLECTOR_POOLER_HOST=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_WORKLOAD_EMAIL=
```

Execute na raiz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/rotate-local-collector-credentials.ps1

powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-monthly-catalog.ps1
```

O primeiro comando rotaciona exclusivamente a role PostgreSQL compartilhada
pelos coletores e o usuário técnico municipal autorizado. Ele atualiza os dois
secrets correspondentes no GitHub e cria o arquivo ignorado
`.collector-credentials.local.json`. Os valores são cifrados pela DPAPI no
escopo `CurrentUser`: somente o mesmo usuário do Windows nesta máquina pode
descriptografá-los. Nenhuma senha é escrita em texto simples, passada em
argumento de processo, exibida no terminal ou registrada no Git.

O piloto exige exatamente abril de 2023 e 1.824 documentos. O segundo comando
carrega o cofre DPAPI automaticamente. Se ainda não houver cofre, mantém a
alternativa de solicitar as senhas com entrada oculta. Em ambos os casos, as
variáveis de ambiente são removidas no bloco `finally`. O replay local respeita
o limite cadastrado de 30 requisições por minuto; tanto o wrapper quanto o
comando Python rejeitam valores acima desse teto.

Para outra competência, desative a contagem específica:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/run-tcm-ba-monthly-catalog.ps1 `
  -MonthFrom 2023-05 -MonthTo 2023-05 -ExpectedDocuments 0
```

Antes de ampliar o intervalo, confirme no Supabase a partição, o número de
documentos, os hashes e o replay idempotente. Backfill grande deve continuar em
lotes mensais; uma falha não autoriza marcar os meses seguintes como vazios.
`ExpectedDocuments 0` desativa somente a comparação com uma contagem conhecida:
o wrapper ainda exige cobertura `complete` e mais de zero documentos. Resposta
vazia, parcial ou sem evento final encerra a execução com erro.

O e-TCM pode ocasionalmente responder HTTP 200 com conteúdo JSF que não atende
ao contrato da tabela. Nessa situação específica, o comando abre uma nova
sessão e refaz a captura integral uma única vez, mantendo o mesmo limitador de
30 requisições por minuto. Para catálogos extensos, o conector também renova
preventivamente a sessão a cada 300 páginas e retoma da página seguinte. Antes
de continuar, ele exige que prestação, total e primeira página permaneçam
idênticos. Erros HTTP, de transporte, banco, Storage ou persistência não entram
nesse retry.

## Piloto comprovado

Para `2021-01`, o replay controlado fechou como `complete`: 1.441 documentos
distintos, 189 observações brutas e 1.442 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 189 observações correspondem a 177 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 177 objetos,
totalizando 12.928.389 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-02`, o replay controlado fechou como `complete`: 1.505 documentos
distintos, 183 observações brutas e 1.506 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 183 observações correspondem a 174 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 174 objetos,
totalizando 10.525.581 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-03`, o replay controlado fechou como `complete`: 1.788 documentos
distintos, 211 observações brutas e 1.789 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 211 observações correspondem a 202 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 202 objetos,
totalizando 11.097.822 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-04`, o replay controlado fechou como `complete`: 1.655 documentos
distintos, 198 observações brutas e 1.656 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, runs, zero
conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 198 observações correspondem a 189 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 189 objetos,
totalizando 10.826.578 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-05`, o replay controlado fechou como `complete`: 1.626 documentos
distintos, 195 observações brutas e 1.627 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 195 observações correspondem a 186 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 186 objetos,
totalizando 10.764.367 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-06`, o replay controlado fechou como `complete`: 1.998 documentos
distintos, 255 observações brutas e 1.999 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 255 observações correspondem a 240 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 240 objetos,
totalizando 16.547.601 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-07`, o replay controlado fechou como `complete`: 1.752 documentos
distintos, 208 observações brutas e 1.753 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 208 observações correspondem a 199 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 199 objetos,
totalizando 11.048.135 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-08`, a primeira tentativa parou antes de fechar a cobertura por
esgotamento transitório de conexões da role técnica no Supabase. A retomada
idempotente fechou como `complete`: 1.901 documentos distintos, 234 observações
brutas e 1.902 registros estruturados, incluindo uma submissão mensal. O gate
selecionou a observação mais recente de cada `stage_index`, confirmou o
manifesto da captura bem-sucedida e preservou a tentativa anterior como falha
resolvida, sem falhas abertas. Doze observações JSF repetiram respostas já
preservadas; as 234 observações correspondem a 222 objetos imutáveis únicos.
A auditoria física releu os 222 objetos, totalizando 13.872.775 bytes, e
confirmou todos os SHA-256 e tamanhos sem divergência.

Para `2021-09`, o replay controlado fechou como `complete`: 1.758 documentos
distintos, 208 observações brutas e 1.759 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 208 observações correspondem a 199 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 199 objetos,
totalizando 11.056.499 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-10`, o replay controlado fechou como `complete`: 1.932 documentos
distintos, 249 observações brutas e 1.933 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas já
preservadas; as 249 observações correspondem a 234 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 234 objetos,
totalizando 16.463.180 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-11`, o replay controlado fechou como `complete`: 1.941 documentos
distintos, 250 observações brutas e 1.942 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas já
preservadas; as 250 observações correspondem a 235 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 235 objetos,
totalizando 16.480.264 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2021-12`, o replay controlado fechou como `complete`: 3.677 documentos
distintos, 456 observações brutas e 3.678 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Vinte e quatro observações JSF repetiram
respostas já preservadas; as 456 observações correspondem a 432 objetos
imutáveis únicos, sem duplicar documentos normalizados. A auditoria física
releu os 432 objetos, totalizando 27.556.976 bytes, e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2022-01`, o replay controlado fechou como `complete`: 1.275 documentos
distintos, 160 observações brutas e 1.276 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 160 observações correspondem a 151 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 151 objetos,
totalizando 10.024.691 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Com esse replay, o gate anual confirmou as 12 competências de `2022-01` a
`2022-12` como `complete`, com 25.865 documentos catalogados, todas as
execuções de controle como `succeeded`, resultados `complete` e nenhuma falha
aberta. A cobertura anual foi comprovada diretamente no banco; não foi inferida
apenas dos registros desta documentação.

Para `2022-02`, o replay controlado fechou como `complete`: 1.790 documentos
distintos, 211 observações brutas e 1.791 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 211 observações correspondem a 202 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 202 objetos,
totalizando 11.067.889 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2022-03`, o replay controlado fechou como `complete`: 1.930 documentos
distintos, 248 observações brutas e 1.931 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 248 observações correspondem a 233 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 233 objetos,
totalizando 16.351.371 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2022-04`, o replay controlado fechou como `complete`: 1.777 documentos
distintos, 210 observações brutas e 1.778 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Nove observações JSF repetiram respostas já
preservadas; as 210 observações correspondem a 201 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 201 objetos,
totalizando 11.037.944 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2022-05`, o replay controlado fechou como `complete`: 2.111 documentos
distintos, 267 observações brutas e 2.112 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 267 observações correspondem a 252 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 252
objetos, totalizando 16.704.908 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2022-06`, o replay controlado fechou como `complete`: 2.213 documentos
distintos, 277 observações brutas e 2.214 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 277 observações correspondem a 262 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 262
objetos, totalizando 16.919.790 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2022-07`, o replay controlado fechou como `complete`: 2.424 documentos
distintos, 297 observações brutas e 2.425 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 297 observações correspondem a 282 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 282
objetos, totalizando 17.455.439 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2022-08`, o replay controlado fechou como `complete`: 2.105 documentos
distintos, 266 observações brutas e 2.106 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 266 observações correspondem a 251 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 251
objetos, totalizando 16.818.605 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2022-09`, o replay controlado fechou como `complete`: 1.963 documentos
distintos, 252 observações brutas e 1.964 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas
já preservadas; as 252 observações correspondem a 237 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 237
objetos, totalizando 16.516.244 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2022-10`, o replay controlado fechou como `complete`: 2.401 documentos
distintos, 295 observações brutas e 2.402 registros estruturados, incluindo uma
submissão mensal. A primeira sonda contou 2.396 documentos, mas o e-TCM
acrescentou cinco documentos durante a janela; o contrato local recusou a
divergência e uma nova sonda confirmou 2.401 antes do replay idempotente. O
gate relacional confirmou manifesto, chaves, MIME, runs, zero conflito e zero
falha aberta. Quinze observações JSF repetiram respostas já preservadas; as 295
observações correspondem a 280 objetos imutáveis únicos, sem duplicar
documentos normalizados. A auditoria física releu os 280 objetos, totalizando
17.412.007 bytes, e confirmou todos os SHA-256 e tamanhos sem divergência.

Para `2022-11`, o replay controlado fechou como `complete`: 2.235 documentos
distintos, 267 observações brutas e 2.236 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 267 observações correspondem a 255 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 255 objetos,
totalizando 14.541.960 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2022-12`, o replay controlado fechou como `complete`: 3.641 documentos
distintos, 453 observações brutas e 3.642 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Vinte e quatro observações JSF repetiram
respostas já preservadas; as 453 observações correspondem a 429 objetos
imutáveis únicos, sem duplicar documentos normalizados. A auditoria física
releu os 429 objetos, totalizando 27.469.130 bytes, e confirmou todos os SHA-256
e tamanhos sem divergência.

Para `2023-01`, o replay controlado fechou como `complete`: 2.023 documentos
distintos, 246 observações brutas e 2.024 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 246 observações correspondem a 234 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 234 objetos,
totalizando 14.042.296 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2023-02`, o replay controlado fechou como `complete`: 2.080 documentos
distintos, 251 observações brutas e 2.081 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 251 observações correspondem a 239 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 239 objetos,
totalizando 14.143.698 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2023-03`, o replay controlado fechou como `complete`: 2.001 documentos
distintos, 244 observações brutas e 2.002 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 244 observações correspondem a 232 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 232 objetos,
totalizando 13.990.039 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Em 24/08/2026, o replay local de `2023-04` terminou com o evento
`collector_tcm_ba_month_completed`: 1.824 documentos, 193 interações brutas e
1.825 registros brutos estruturados. A consulta independente ao banco confirmou
a partição `competence:2023-04` como `complete`, execução `succeeded` e 1.824
registros observados.

No mesmo dia, a competência `2023-05` também foi fechada como `complete`. O
coletor catalogou 2.345 documentos, preservou 245 interações e inseriu 2.346
registros brutos estruturados: 2.345 documentos e uma submissão mensal. A
auditoria independente confirmou 2.345 chaves oficiais distintas, nenhuma
ligação órfã, 245 execuções de persistência bem-sucedidas e nenhum artefato
com status HTTP fora da faixa 2xx.

A competência `2023-06` foi fechada na sequência como `complete`, com 2.741
documentos catalogados, 285 interações preservadas e 2.742 registros brutos
estruturados: 2.741 documentos e uma submissão mensal. A auditoria direta no
banco confirmou 2.741 chaves oficiais e 2.741 chaves de idempotência distintas,
nenhuma falha de coleta registrada e nenhum artefato com status HTTP fora da
faixa 2xx. Os 285 registros de artefato representam 282 objetos e hashes únicos;
as três repetições são observações imutáveis de respostas JSF idênticas, não
documentos duplicados na projeção normalizada.

Para `2023-07`, o catálogo registrou 2.331 documentos, 244 interações e 2.332
registros brutos estruturados. A partição também fechou como `complete`, com
2.331 chaves oficiais e de idempotência distintas, nenhuma falha registrada e
nenhum status HTTP fora da faixa 2xx. As 244 observações correspondem a 241
objetos e hashes únicos; novamente, as três repetições preservam respostas JSF
idênticas e não alteram a contagem normalizada de documentos.

Para `2023-08`, uma primeira captura encontrou uma resposta HTTP 200 sem a
tabela documental e falhou de forma segura, sem fechar a partição como vazia.
Uma reprodução diagnóstica preservou 243 respostas e comprovou que o catálogo
continha 2.327 documentos. Após a proteção de nova sessão para essa falha de
contrato, o replay persistente fechou a competência como `complete`: 2.327
documentos, 243 observações brutas e 2.328 registros estruturados, sendo uma
submissão mensal. O gate relacional confirmou manifesto, sequência, MIME,
HTTP, chaves e runs, com zero conflito e zero falha aberta. Por fim, 240 objetos
únicos foram relidos do bucket privado (7.144.760 bytes); todos os SHA-256 e
tamanhos coincidiram com o banco.

Para `2023-09`, o replay controlado fechou como `complete`: 3.056 documentos,
316 observações brutas e 3.057 registros estruturados, incluindo uma submissão
mensal. O gate relacional confirmou contagens, manifesto, chaves, MIME, status
dos runs e ausência de falhas abertas. A auditoria física releu 313 objetos
únicos do bucket privado, totalizando 8.628.962 bytes, sem divergência de
SHA-256 ou tamanho.

Para `2023-10`, o replay controlado também fechou como `complete`: 1.968
documentos distintos, 207 observações brutas e 1.969 registros estruturados,
incluindo uma submissão mensal. O gate relacional confirmou o manifesto, os
204 objetos físicos únicos, as chaves, MIME, status dos runs e zero falha
aberta ou conflito de identidade. A auditoria física releu 6.435.160 bytes do
bucket privado, sem divergência de SHA-256 ou tamanho.

Para `2023-11`, o replay controlado fechou como `complete`: 2.666 documentos
distintos, 277 observações brutas e 2.667 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou o manifesto, os 274 objetos
físicos únicos, as chaves, MIME, status dos runs e zero falha aberta ou conflito
de identidade. A auditoria física releu 7.837.823 bytes do bucket privado, sem
divergência de SHA-256 ou tamanho.

Para `2023-12`, três sessões independentes falharam de forma segura na página
396, sempre após o e-TCM responder HTTP 200 com um HTML sem tabela, formulário
JSF ou sinal explícito de expiração. A renovação preventiva atravessou esse
ponto e o replay fechou como `complete`: 4.746 documentos distintos, 496
observações brutas e 4.747 registros estruturados, incluindo uma submissão
mensal. O gate relacional confirmou manifesto, chaves, MIME, runs, zero conflito
e zero falha aberta. As observações correspondem a 490 objetos imutáveis únicos;
a auditoria física releu 14.541.603 bytes e confirmou todos os SHA-256 e
tamanhos sem divergência.

Para `2024-01`, o primeiro contrato retornou uma estrutura inválida e foi
descartado sem fechar a competência. A repetição controlada concluiu como
`complete`: 2.926 documentos distintos, 303 observações brutas e 2.927
registros estruturados, incluindo uma submissão mensal. O gate relacional
confirmou manifesto, chaves, MIME, runs, zero conflito e zero falha aberta. As
observações correspondem a 300 objetos imutáveis únicos; a auditoria física
releu 8.308.835 bytes e confirmou todos os SHA-256 e tamanhos sem divergência.

Para `2024-02`, o replay controlado fechou como `complete`: 2.615 documentos
distintos, 272 observações brutas e 2.616 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 269 objetos
imutáveis únicos; a auditoria física releu 7.720.263 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-03`, o replay controlado fechou como `complete`: 2.787 documentos
distintos, 289 observações brutas e 2.788 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 286 objetos
imutáveis únicos; a auditoria física releu 8.065.120 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-04`, o replay controlado fechou como `complete`: 2.827 documentos
distintos, 293 observações brutas e 2.828 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 290 objetos
imutáveis únicos; a auditoria física releu 8.142.875 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-05`, o replay controlado fechou como `complete`: 2.685 documentos
distintos, 279 observações brutas e 2.686 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 276 objetos
imutáveis únicos; a auditoria física releu 7.863.844 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-06`, o replay controlado fechou como `complete`: 3.065 documentos
distintos, 328 observações brutas e 3.066 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 322 objetos
imutáveis únicos; a auditoria física releu 11.136.457 bytes e confirmou todos
os SHA-256 e tamanhos sem divergência.

Para `2024-07`, o replay controlado fechou como `complete`: 3.202 documentos
distintos, 342 observações brutas e 3.203 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 336 objetos
imutáveis únicos; a auditoria física releu 11.399.733 bytes e confirmou todos
os SHA-256 e tamanhos sem divergência.

Para `2024-08`, a primeira execução encontrou uma resposta HTTP 200 sem a
tabela documental e falhou de forma segura, sem fechar a competência como
vazia. Uma reprodução somente leitura confirmou 3.063 documentos em 328
interações. O replay persistente, limitado a 30 requisições por minuto e com
essa cardinalidade exigida, fechou como `complete`: 3.063 documentos distintos,
328 observações brutas e 3.064 registros estruturados, incluindo uma submissão
mensal. O gate relacional confirmou manifesto, chaves, MIME, runs, zero
conflito e zero falha aberta. As observações correspondem a 322 objetos
imutáveis únicos; a auditoria física releu 11.121.416 bytes e confirmou todos
os SHA-256 e tamanhos sem divergência.

Para `2024-09`, o replay controlado fechou como `complete`: 2.805 documentos
distintos, 291 observações brutas e 2.806 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 288 objetos
imutáveis únicos; a auditoria física releu 8.112.725 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-10`, o replay controlado fechou como `complete`: 3.223 documentos
distintos, 344 observações brutas e 3.224 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 338 objetos
imutáveis únicos; a auditoria física releu 11.461.567 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-11`, o replay controlado fechou como `complete`: 2.998 documentos
distintos, 310 observações brutas e 2.999 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 307 objetos
imutáveis únicos; a auditoria física releu 8.496.548 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2024-12`, o replay controlado fechou como `complete`: 4.386 documentos
distintos, 547 observações brutas e 4.387 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 517 objetos
imutáveis únicos; a auditoria física releu 33.330.729 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-01`, o replay controlado fechou como `complete`: 1.627 documentos
distintos, 195 observações brutas e 1.628 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 186 objetos
imutáveis únicos; a auditoria física releu 10.737.358 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-02`, o replay controlado fechou como `complete`: 2.694 documentos
distintos, 324 observações brutas e 2.695 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 309 objetos
imutáveis únicos; a auditoria física releu 17.884.087 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-03`, o replay controlado fechou como `complete`: 2.569 documentos
distintos, 311 observações brutas e 2.570 registros estruturados, incluindo uma
submissão mensal. A sondagem preliminar havia encontrado 2.568 documentos; uma
segunda consulta, com novo hash do detalhe oficial, confirmou os 2.569 capturados
pelo replay. O gate relacional confirmou manifesto, chaves, MIME, runs, zero
conflito e zero falha aberta. As observações correspondem a 296 objetos imutáveis
únicos; a auditoria física releu 17.643.806 bytes e confirmou todos os SHA-256 e
tamanhos sem divergência.

Para `2025-04`, o replay controlado fechou como `complete`: 2.584 documentos
distintos, 313 observações brutas e 2.585 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 298 objetos
imutáveis únicos; a auditoria física releu 17.647.405 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-05`, o replay controlado fechou como `complete`: 2.766 documentos
distintos, 342 observações brutas e 2.767 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 324 objetos
imutáveis únicos; a auditoria física releu 20.528.836 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-06`, o replay controlado fechou como `complete`: 2.830 documentos
distintos, 337 observações brutas e 2.831 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 322 objetos
imutáveis únicos; a auditoria física releu 18.170.979 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-07`, o replay controlado fechou como `complete`: 2.940 documentos
distintos, 348 observações brutas e 2.941 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 333 objetos
imutáveis únicos; a auditoria física releu 18.377.734 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-08`, o replay controlado fechou como `complete`: 2.819 documentos
distintos, 336 observações brutas e 2.820 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 321 objetos
imutáveis únicos; a auditoria física releu 18.142.672 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-09`, o replay controlado fechou como `complete`: 3.037 documentos
distintos, 369 observações brutas e 3.038 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 351 objetos
imutáveis únicos; a auditoria física releu 21.089.679 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-10`, uma primeira execução falhou de forma segura durante uma resposta
transitória não estruturada do Storage, sem aprovar a competência. Após o retry
limitado de upload, o replay idempotente fechou como `complete`: 2.740 documentos
distintos, 328 observações brutas e 2.741 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As observações correspondem a 313 objetos
imutáveis únicos; a auditoria física releu 17.987.298 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-11`, o replay controlado fechou como `complete`: 3.048 documentos
distintos, 370 observações brutas e 3.049 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. As 370 observações correspondem a 370 objetos
imutáveis únicos; a auditoria física releu 21.099.049 bytes e confirmou todos os
SHA-256 e tamanhos sem divergência.

Para `2025-12`, a primeira tentativa foi bloqueada após o e-TCM perder a tabela
de documentos durante a paginação. Com a recuperação limitada de sessão, o
replay retomou a página afetada somente depois de revalidar a prestação, o total
e a primeira página do snapshot. A competência fechou como `complete`: 5.031
documentos distintos, 614 observações brutas e 5.032 registros estruturados,
incluindo uma submissão mensal. O gate relacional confirmou manifesto, chaves,
MIME, runs, zero conflito e zero falha aberta. As 614 observações correspondem a
614 objetos imutáveis únicos; a auditoria física releu 35.105.094 bytes e
confirmou todos os SHA-256 e tamanhos sem divergência.

Para `2026-01`, o replay controlado fechou como `complete`: 2.286 documentos
distintos, 272 observações brutas e 2.287 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; por isso, as 272 observações correspondem a 260 objetos imutáveis
únicos, sem duplicar documentos normalizados. A auditoria física releu os 260
objetos, totalizando 14.539.786 bytes, e confirmou todos os SHA-256 e tamanhos
sem divergência.

Para `2026-02`, o replay controlado fechou como `complete`: 3.365 documentos
distintos, 402 observações brutas e 3.366 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Dezoito observações JSF repetiram respostas
já preservadas; as 402 observações correspondem a 384 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 384 objetos,
totalizando 21.708.511 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2026-03`, o replay controlado fechou como `complete`: 2.391 documentos
distintos, 283 observações brutas e 2.392 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Doze observações JSF repetiram respostas já
preservadas; as 283 observações correspondem a 271 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 271 objetos,
totalizando 14.740.564 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2026-04`, o replay controlado fechou como `complete`: 3.354 documentos
distintos, 401 observações brutas e 3.355 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Dezoito observações JSF repetiram respostas
já preservadas; as 401 observações correspondem a 383 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 383 objetos,
totalizando 21.690.452 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2026-05`, o replay controlado fechou como `complete`: 2.532 documentos
distintos, 308 observações brutas e 2.533 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Quinze observações JSF repetiram respostas já
preservadas; as 308 observações correspondem a 293 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 293 objetos,
totalizando 17.538.244 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2026-06`, o replay controlado fechou como `complete`: 3.340 documentos
distintos, 399 observações brutas e 3.341 registros estruturados, incluindo uma
submissão mensal. O gate relacional confirmou manifesto, chaves, MIME, runs,
zero conflito e zero falha aberta. Dezoito observações JSF repetiram respostas
já preservadas; as 399 observações correspondem a 381 objetos imutáveis únicos,
sem duplicar documentos normalizados. A auditoria física releu os 381 objetos,
totalizando 21.660.382 bytes, e confirmou todos os SHA-256 e tamanhos sem
divergência.

Para `2026-07`, nenhum replay foi aprovado. Duas sessões independentes do
e-TCM não confirmaram exatamente uma prestação mensal para a competência. A
partição foi registrada como `blocked`, com zero registros observados e a razão
operacional preservada. Esse estado não significa ausência de documentos nem
prestação vazia; exige nova tentativa contra a fonte oficial antes de qualquer
publicação.

A partição mensal aponta para o run de controle; cada interação JSF preservada
possui seu próprio run idempotente. Por isso, a auditoria relaciona os artefatos
pela fonte, schema, competência e `started_at` dentro da janela do run de
controle, exige que todos os runs-filhos tenham concluído com sucesso e só então
recompõe o manifesto pela ordem de `stage_index`. O campo `created_at` não serve
como limite superior dessa relação: o commit de um run-filho pode ocorrer
milissegundos depois do fechamento lógico do controle. Uma junção direta entre
o run da partição e `raw_artifacts.collection_run_id` também não representa essa
linhagem.

Idempotência possui duas camadas. Cada nova observação HTTP permanece
imutável, inclusive quando o JSF altera tokens de sessão sem mudar o documento.
As projeções normalizadas devem reconciliar essas observações pela chave
oficial, tipo, competência, parser e conteúdo; nunca pela posição na página.
Assim preservamos a prova bruta sem contar o mesmo documento duas vezes no
produto público.

As respostas AJAX do JSF chegam como `text/xml`. Para respeitar a lista de MIME
types do bucket privado, o persistidor registra o equivalente
`application/xml` no artefato e mantém o `Content-Type` literal da origem nos
headers preservados. Os bytes e o SHA-256 não são alterados.

## Contrato de download dos PDFs

O download possui duas requisições inseparáveis dentro da mesma sessão JSF. O
POST do botão do documento devolve um XML preparatório; esse XML deve apontar
uma única vez para o endpoint oficial `PdfReadOnly/downloadDocumento.seam`. O
GET seguinte deve devolver HTTP 200, `application/pdf`, bytes iniciados por
`%PDF-` e marcador final `%%EOF`.

Antes do POST, o coletor recompõe a competência e a página correspondentes à
posição global do documento. Total mensal e metadados podem ser comparados ao
catálogo imutável; qualquer drift bloqueia o download. O limite do PDF é
separado do limite de HTML/XML. Esta etapa ainda não autoriza download em massa
nem publicação financeira: primeiro será comprovada a persistência filha,
incluindo leitura física do Storage e vínculo ao registro bruto do catálogo.
## Piloto de persistência documental

O comando documental exige um catálogo mensal já classificado como `complete`.
Ele recusa competências com lacunas, posições repetidas, chaves conflitantes ou
contagem diferente da cobertura registrada. PDFs já preservados são excluídos
da fila por sua chave oficial. O banco remoto também precisa conter a migration
`20260828113000_authorize_tcm_ba_monthly_documents_storage.sql`; sem ela, o
Storage recusa o corredor documental e a execução falha de forma fechada, sem
marcar o mês como coletado.

Execute inicialmente um único documento:

```powershell
$env:PYTHONPATH = "workers/collectors/src"
python -B -m barreiras_collectors.commands.collect_tcm_ba_documents `
  --competence 01/2021 `
  --max-documents 1 `
  --requests-per-minute 30
```

O limite aceito é de um a cinco documentos e nunca mais de 30 requisições por
minuto. Cada lote cria uma execução de controle própria. O checkpoint registra
o total esperado, quantos PDFs já estavam preservados, quantos foram baixados e
quantos restam. A partição `documents:AAAA-MM` permanece `partial` até que o
último PDF seja validado; somente então recebe `complete`.

A cadeia de evidência é `artefato do catálogo -> XML preparatório -> PDF`. Os
dois filhos são gravados por hash no bucket privado, relidos e validados antes
do commit relacional. Um piloto só é aprovado após consulta viva ao PostgreSQL
e releitura independente dos objetos. Este comando ainda não extrai números,
não interpreta contas e não publica projeções financeiras.
### Evidência do primeiro piloto documental

Em 28/08/2026, o primeiro piloto real da competência 01/2021 preservou um dos
1.441 documentos catalogados. A partição documental encerrou a execução como
partial, com um PDF preservado e 1.440 restantes. O campo completed_at indica
que aquele lote terminou; não significa que a competência mensal esteja
completa. Apenas status complete, total recomposto e zero restante fecham o mês
documental.

O piloto produziu dois artefatos filhos: o XML preparatório de 1.248 bytes e o
PDF oficial de 1.718.309 bytes. Ambos retornaram HTTP 200, foram relidos do
bucket privado e tiveram tamanho e SHA-256 recomputados sem divergência. O PDF
também confirmou os marcadores de abertura e encerramento. A cadeia relacional
ligou o registro bruto do catálogo ao XML e, deste, ao PDF. Duas tentativas
anteriores permanecem no histórico como falhas: uma por autorização do corredor
do Storage e outra pelo plano de consulta antigo. Elas não são apagadas
silenciosamente.

O wrapper recomendado para os próximos lotes é:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tcm-ba-document-pilot.ps1 -Competence 01/2021 -MaxDocuments 5 -RequestsPerMinute 30

O selo TCM_BA_DOCUMENT_PILOT_APPROVED só aparece quando exatamente um evento
final recompõe o total esperado, preserva de um a cinco PDFs, avança a cobertura
e mantém partial enquanto houver documentos pendentes. O limite de 30 RPM é
fechado e as credenciais continuam protegidas pelo usuário atual do Windows.

### Evidência do segundo piloto documental

Ainda em 28/08/2026, um segundo lote controlado de 01/2021 preservou cinco PDFs
e seus cinco XMLs preparatórios. A cobertura cumulativa avançou para 6 dos 1.441
documentos, com 1.435 restantes e estado `partial`. A auditoria independente
releu os dez objetos privados, totalizou 8.028.343 bytes, recalculou tamanhos e
SHA-256 e confirmou dez conteúdos físicos distintos, cinco vínculos com o
catálogo e zero falha aberta na execução atual. As duas falhas antigas continuam
preservadas como histórico e não interferem na aprovação do lote íntegro.

A partir deste contrato, o wrapper executa o auditor somente leitura antes de
emitir `TCM_BA_DOCUMENT_PILOT_APPROVED`. O auditor abre a transação PostgreSQL
como `read only`, reconcilia checkpoint, métricas, status, linhagem e MIME e
relê cada XML e PDF do bucket privado. Qualquer contador divergente, falha atual,
objeto ausente, hash ou tamanho incompatível, chave fora do corredor de conteúdo
ou assinatura documental inválida bloqueia a aprovação. Uma partição `partial`
nunca é apresentada como mês completo.

## Drenagem documental automatizada

O runner hospedado do GitHub não alcançou o e-TCM em 28/08/2026: quatro
tentativas de abertura HTTPS expiraram antes da primeira resposta. Por isso, o
workflow `collect-tcm-ba-documents.yml` permanece manual para diagnóstico e não
é tratado como mecanismo de cobertura. A drenagem automática usa uma tarefa do
Windows, no mesmo ambiente em que os lotes reais foram validados.

A tarefa `Barreiras360-TCMBA-Documents` executa no máximo um lote a cada 15
minutos, com até cinco documentos e limite fixo de 30 requisições por minuto.
Ela roda apenas no usuário atual, em nível limitado, reutiliza o cofre DPAPI e
ignora nova instância enquanto a anterior estiver ativa. A cadência mínima de 15
minutos mantém no máximo vinte documentos por hora e não abre uma segunda
execução se auditoria, OCR ou processamento ainda estiverem ativos. Para
instalar ou atualizar:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-tcm-ba-document-schedule.ps1 -IntervalMinutes 15 -StartNow

No agendamento local, um planejador somente leitura escolhe a competência cronológica
mais antiga, a partir de 2021, que possua catálogo mensal completo e cobertura
documental ainda incompleta. Uma competência sem catálogo completo não é
classificada como vazia e não recebe partição documental artificial. Ela
permanece como lacuna de cobertura até a coleta íntegra do catálogo.

O planejador local emite antes de cada lote um evento sanitizado
`tcm_ba_document_plan`, com competência, total esperado, PDFs já preservados,
restantes e estado de cobertura. O evento não contém nomes, credenciais, URLs
privadas nem conteúdo documental. A linha seguinte conserva apenas a competência
`MM/AAAA`, usada pelo wrapper como entrada validada. Se não houver competência
elegível, o evento registra cobertura `complete` e não inventa um mês vazio.
Para consultar o avanço sem abrir sessão no e-TCM nem alterar o banco:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tcm-ba-document-pilot.ps1 -AutoCompetence -PlanOnly

Para auditar novamente o último lote de uma competência sem coletar ou alterar
qualquer registro:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-tcm-ba-document-pilot.ps1 -Competence 01/2021 -AuditOnly

O modo `AuditOnly` exige um único evento `PASS` da competência exata. Ele abre o
banco somente para leitura, baixa os XMLs e PDFs do último lote, recalcula tamanho
e SHA-256 e confere cobertura, linhagem, tipos de mídia e falhas abertas. O modo
`ReportOnly` executa somente leituras agregadas e reconcilia páginas,
famílias documentais, segmentos e campos contratuais e candidatos de empenho.
Ele não baixa objetos nem substitui a auditoria física de uma competência.

Cada rodada preserva XML e PDF, fecha a execução como `partial` enquanto houver
itens pendentes e chama o auditor relacional e físico antes do selo de
aprovação. Ausência de objetos, divergência de hash, tamanho, MIME, linhagem ou
contador faz o workflow falhar. Se não existir competência elegível, a rodada
termina sem coleta e sem alterar estados no banco.

Depois do gate físico, o mesmo wrapper processa no máximo cinco PDFs já
preservados. O processador relê o objeto privado, recomputa o SHA-256 e registra
cada página em `raw.document_pages` com versão do extrator. Página sem texto
embutido permanece explicitamente nula para OCR; não é tratada como página
vazia. A transação cria o job `tcm_ba_document_text` somente junto com as
páginas idempotentes. O selo final é bloqueado por PDF inválido, falha de
processamento, lote vazio ou contadores de páginas incompatíveis. Esta etapa
ainda não classifica o documento, não extrai empenhos e não publica valores.

O OCR seguinte usa uma fila obrigatoriamente escopada à fonte TCM-BA; ele nunca
consome páginas do Diário Oficial nem registra origem incorreta. São processadas
até 30 páginas escaneadas por rodada, com método declarado como OCR e versão
tcm-ba-document-ocr-text/1.0.0. O texto OCR complementa a página nula sem
substituir o registro do extrator PDF nem ocultar a técnica utilizada.

### Cobertura privada dos candidatos de empenho

Depois do processamento, `report_tcm_ba_commitments` reconcilia cada PDF com
páginas verificadas contra o job idempotente da versão atual. O gate exige que
todo artefato elegível tenha um job bem-sucedido e rejeita ausências,
duplicidades, payloads inválidos e falhas abertas. Artefatos sem candidato são
contados explicitamente, pois um extrator determinístico pode não reconhecer o
leiaute sem que isso prove ausência de nota de empenho no documento.

Em 30/08/2026, o primeiro fechamento da versão 1.0 encontrou 378 artefatos
eligíveis, 228 processados e 145 ausentes. O backlog foi drenado em lotes
idempotentes de 50, 50 e 45; a reconciliação final fechou 378 de 378, sem
falhas. Como essa versão produziu zero candidatos, o resultado permaneceu um
diagnóstico do extrator, não uma conclusão financeira.

A auditoria dos leiautes preservados mostrou que o e-TCM imprime o marcador
NOTA DE EMPENHO separado do campo rotulado EMPENHO: e utiliza variantes de
OCR nos demais rótulos. A versão 1.1 passou a reconhecer somente essa estrutura
oficial, normalizar o número e remover apenas candidatos com identidade extraída
idêntica; notas de mesmo número com credor ou data diferentes continuam
separadas.

O replay integral da versão 1.1 reconciliou 388 de 388 PDFs elegíveis. Foram
registrados 98 candidatos em 94 artefatos e 294 artefatos explicitamente sem
candidato; não houve ausência, duplicidade, payload inválido nem falha aberta.
Todos os 98 candidatos permaneceram incompletos e privados, aguardando revisão
e novos extratores de campos tabulares. O gate retornou PASS para a cobertura
do processamento, mas não autorizou publicar nenhum empenho ou valor.

A versão 1.2 corrigiu um risco em que espaços genéricos podiam atravessar a
quebra de linha e interpretar o rótulo seguinte como valor do campo anterior.
Os campos em linha separada passaram a exigir vínculo explícito com o rótulo e
validação específica de data, credor, valor ou dotação. O replay preservou o
mesmo universo de 98 candidatos e reconciliou 398 de 398 PDFs, sem falhas,
ausências, duplicidades ou payloads inválidos. Em 22 candidatos, somente a
dotação permaneceu ausente; nenhum deles foi marcado como completo ou
publicável, pois a dotação ainda não pôde ser extraída com segurança.

A versão 1.3 relê o PDF privado, confere novamente o SHA-256 e usa as
coordenadas do texto somente quando há uma única nota na página e seleciona
a célula de melhor escore alinhada ao rótulo de dotação. Empates, rótulos
fragmentados e
páginas sem coordenadas permanecem incompletos; nenhum resultado é publicado.
O replay de 30/08/2026 reconciliou 413 de 413 PDFs elegíveis e manteve os 98
candidatos. Dezenove dotações foram recuperadas com evidência de página, ordem
dos blocos, versão do parser e relação geométrica `below`; cinco candidatos
ficaram completos e quatorze ainda carecem de outros campos. Não houve
resultado inválido, duplicidade, artefato ausente nem falha aberta. Todos os
candidatos continuam em `needs_review` no domínio privado.
A auditoria geométrica posterior mostrou que as 19 páginas tinham uma única
etiqueta, porém de três a seis sequências numéricas plausíveis na mesma coluna.
Por isso a versão 1.4 substituiu o critério de melhor distância por dois gates:
a primeira célula deve ter escore máximo 20 e ficar ao menos 5 pontos à frente
da segunda. Se qualquer condição falhar, a dotação continua ausente. O replay
final reconciliou 418 de 418 PDFs, preservou os 98 candidatos e aceitou somente
13 dotações; quatro candidatos ficaram completos e nove ainda carecem de outros
campos. Seis associações aceitas no benchmark 1.3 foram descartadas. Não houve
duplicidade, payload inválido, artefato ausente nem falha aberta, e os 98
resultados permanecem privados em `needs_review`.

Após o primeiro ciclo agendado com a versão 1.4, a cobertura passou a 423 de
423 PDFs, 9.078 páginas e zero falha aberta. O relatório agregado de campos
reconciliou os mesmos 98 candidatos e quatro completos. Permaneceram ausentes
85 dotações, 74 valores, 63 datas e 56 credores; 50 candidatos continham os
quatro campos ausentes. A distribuição não inclui nomes, documentos fiscais
nem trechos dos PDFs e bloqueia a execução se os totais divergirem da cobertura
principal. Esses números orientam o próximo extrator espacial, mas não tornam
nenhum candidato publicável sem o restante dos gates e revisão.

A versão 1.5 aplicou a mesma régua geométrica fail-closed aos rótulos de data e
valor. O replay privado e append-only foi limitado a 20 lotes de 50, relendo os
objetos autenticados e recomputando seus hashes, sem executar nova coleta. A
cobertura inicial fechou 433 de 433 PDFs e preservou os mesmos 98 candidatos,
quatro completos, sem falha, duplicidade ou payload inválido. Durante a
validação final chegaram mais cinco PDFs; o replay incremental os classificou
sem novos candidatos e o gate definitivo fechou 438 de 438. Foram associados 37
valores monetários com evidência de página e blocos; a ausência de valor caiu
de 74 para 37. Nenhuma data passou os gates no acervo real, e por isso a
ausência de data permaneceu em 63, sem relaxar distância ou ambiguidade. As 13
dotações da versão 1.4 foram preservadas. Todos os resultados continuam
privados em `needs_review`; o gate confirmou zero evidência espacial inválida
e nenhum valor foi publicado.

A versão 1.6 estendeu a régua somente ao nome do credor. Antes do replay, um
benchmark privado e sem persistência contabilizou os 56 candidatos que ainda
careciam desse campo: 47 tinham um único rótulo `CREDOR` e um único valor
geométrico compatível; nove não tinham rótulo reconhecível. O replay append-only
reprocessou os PDFs com nova versão de idempotência e, com a chegada de quinze
artefatos desde o fechamento anterior, reconciliou 453 de 453 PDFs e 103
candidatos. Cinquenta e um nomes de credor ficaram associados a evidência de
página, blocos, versão do parser e relação geométrica; nove permaneceram
ausentes. O relatório fechou com quatro candidatos completos, zero ausência de
artefato, duplicidade, payload inválido, evidência espacial inválida ou falha
aberta. O benchmark pós-replay examinou exatamente os nove restantes e
classificou todos como `no_label`, sem forçar associação. Os logs HTTP privados
foram silenciados e os eventos por artefato passaram a `DEBUG` sem hash; em
`INFO` permanece somente o resumo agregado. Todos os candidatos continuam
privados em `needs_review` e nenhum empenho foi publicado.

A versão 1.7 tratou exclusivamente datas de emissão ou de empenho escritas na
mesma linha de um rótulo oficial completo. O benchmark privado anterior ao
replay encontrou 74 candidatos sem data: 27 tinham uma única data ligada a um
rótulo explícito; 32 continham múltiplos rótulos ou valores e 15 não tinham
evidência suficiente. O replay append-only reconciliou 488 de 488 PDFs, 9.756
páginas e 124 candidatos. Vinte e seis datas novas foram associadas com
evidência de página e bloco `inline`; uma das 27 ocorrências já estava resolvida
por regra espacial na versão reprocessada. Permaneceram 48 datas ausentes. O
benchmark posterior examinou exatamente essas 48 e encontrou zero associação
estrita restante: 33 tinham múltiplos rótulos, 13 múltiplas datas sem vínculo e
duas apenas uma data sem rótulo. A cobertura fechou com zero falha aberta,
duplicidade, payload inválido ou evidência espacial inválida. Rótulos genéricos
como `DATA` e `DT` continuam apenas no diagnóstico e nunca autorizam a extração.
Todos os resultados permanecem privados em `needs_review`; nenhum empenho foi
publicado.

A versão 1.8 acrescentou um segundo gate para repetições inline: somente aceita
quando todas as ocorrências ligadas a rótulos oficiais completos contêm a mesma
data, registrando também `occurrence_count` na evidência. O benchmark privado
anterior ao replay dividiu os 33 casos com múltiplas datas explícitas em oito
consensos integrais e 25 conflitos. O replay append-only alcançou 513 de 513
PDFs e 9.959 páginas, incorporando 25 artefatos que chegaram após a versão 1.7,
sem novos candidatos. As oito datas consensuais foram recuperadas e a ausência
de data caiu de 48 para 40. O benchmark posterior contabilizou exatamente as 40
pendências: 25 conflitos, 13 páginas com múltiplas datas sem vínculo e duas com
uma única data sem rótulo; nenhum consenso seguro permaneceu. A cobertura fechou
sem falha aberta, ausência, duplicidade, payload inválido ou evidência espacial
inválida. Os 124 candidatos continuam privados em `needs_review`; nenhum valor
foi publicado.

Em 30/08/2026, o modo privado e somente leitura
`-CommitmentBudgetBenchmarkOnly` reconciliou os 110 candidatos que ainda não
tinham `budget_allocation`, distribuídos em 105 PDFs, sem falha de leitura ou
artefato incompatível. Nenhuma nova associação satisfez a régua conservadora:
101 páginas não tinham rótulo oficial exato e todas continham múltiplas
sequências numéricas estruturalmente plausíveis; nove tinham o rótulo
`CLASSIFICAÇÃO ORÇAMENTÁRIA`, mas seis valores estavam fora da distância máxima
e três eram geometricamente ambíguos. Em treze das 101 páginas apareceu a
expressão de classificação como prefixo, porém o sufixo continha somente texto,
sem dígitos; dez mencionavam fonte de recurso. O gate contabilizou 110 de 110 e
retornou `PASS`, mas recuperou zero dotações. Portanto, as ausências permanecem
explícitas e privadas: preencher qualquer uma delas automaticamente exigiria
escolher entre valores concorrentes sem evidência suficiente.

Em 31/08/2026, a leitura privada e somente agregada dos 44 candidatos ainda
sem `amount_text`, distribuídos em 40 PDFs, validou o hash de cada objeto antes
de derivar o layout. O gate contabilizou 44 de 44, sem falha de artefato ou de
candidato, e recuperou zero valores: 37 páginas não tinham rótulo oficial, uma
tinha rótulo mas nenhum valor monetário compatível e seis tinham múltiplos
valores geometricamente concorrentes. Não houve página sem layout embutido,
rótulo duplicado nem página com mais de um candidato. O modo privado
`-CommitmentAmountBenchmarkOnly` reproduz esse diagnóstico sem registrar
valores, nomes, hashes, caminhos ou trechos. Um `PASS` comprova a contabilização
integral das pendências; não autoriza escolher um dos valores concorrentes nem
preencher os campos ausentes.

Em 29/08/2026, a tarefa das 12h29 avançou automaticamente de 43 para 48 PDFs
preservados em `01/2021`, deixando 1.393 de 1.441 pendentes. O resultado do
Agendador foi confrontado com o planejador somente leitura; o código `0` do
Windows não foi aceito sozinho como prova de avanço.

Na rodada automática das 13h29, a cobertura subiu de 48 para 53 PDFs. O
relatório sanitizado e somente leitura confirmou cinco PDFs com páginas
canônicas, 107 páginas totais, todas com texto embutido, nenhuma aguardando OCR
e nenhum job de texto falho. O relatório retornou approved=true; nenhum conteúdo
de página, credencial ou chave de objeto foi exposto.

Em 30/08/2026, a rodada das 01h29 preservou mais cinco PDFs e cinco XMLs de
preparação. A auditoria física releu os dez objetos, recomputou 16.410.792 bytes
e dez hashes distintos, confirmou cinco vínculos exatos com o catálogo e zero
falha aberta no lote. A competência `01/2021` avançou para 88 de 1.441 PDFs.
Como a execução completa, incluindo extração, classificação e gates privados,
terminou antes da janela seguinte, a cadência foi reduzida para 15 minutos sem
alterar o teto de cinco documentos por lote, o pico de 30 RPM ou a proteção
`IgnoreNew` contra sobreposição.

### Evidência da seleção automática local

Em 28/08/2026, o modo `-AutoCompetence` selecionou `01/2021` sem entrada
manual e preservou o 17º documento do catálogo de 1.441 itens. O auditor releu
o XML e o PDF, totalizou 53.253 bytes, confirmou dois hashes físicos distintos,
um vínculo exato com o catálogo e zero falha aberta na execução. A tentativa do
runner hospedado continua preservada como a terceira falha histórica; não foi
apagada nem convertida em sucesso.
