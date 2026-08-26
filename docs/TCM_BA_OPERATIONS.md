# Operação do catálogo mensal do TCM-BA

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
