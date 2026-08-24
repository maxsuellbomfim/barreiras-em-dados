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
30 requisições por minuto. Erros HTTP, de transporte, banco, Storage ou
persistência não entram nesse retry.

## Piloto comprovado

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
