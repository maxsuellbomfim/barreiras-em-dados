# Collectors

Coletores adquirem e descrevem respostas externas; não normalizam entidades nem
publicam dados. O primeiro módulo é um cliente da API do Querido Diário.

## Teste local sem dependências

No PowerShell, a partir da raiz:

```powershell
$env:PYTHONPATH='workers/collectors/src'
python -m unittest discover -s tests/collectors -p 'test_*.py'
```

Os testes usam transporte, relógio e aleatoriedade injetados. Nenhum teste
unitário acessa a rede.

## Persistência local da primeira janela

O modo padrão de desenvolvimento não exige banco, conta de nuvem ou segredo:

```powershell
$env:PYTHONPATH='workers/collectors/src'
$env:PERSISTENCE_MODE='filesystem'
$env:LOCAL_DATA_DIRECTORY='data/local-evidence'
python -m barreiras_collectors.commands.collect_querido_diario `
  --since 2026-06-10 `
  --until 2026-06-10
```

O comando exige uma janela de no máximo sete dias. Ele salva a resposta JSON em
uma chave derivada do SHA-256, restaura os bytes e grava um manifesto canônico.
Repetir a mesma janela reutiliza o objeto e o manifesto. Alteração posterior,
travessia de diretório ou conflito de identidade interrompem a execução.

`data/` é ignorada pelo Git. O modo `filesystem` é recusado em staging e
produção.

## Adaptador PostgreSQL + Supabase Storage

O adaptador anterior continua disponível apenas para um ambiente isolado:

```powershell
python -m pip install -e ".[postgres,storage]"
$env:PERSISTENCE_MODE='postgres-supabase'
```

Ele exige:

- `DATABASE_URL` com o login `collector_querido_diario`;
- `SUPABASE_URL`;
- `SUPABASE_PUBLISHABLE_KEY`;
- `SUPABASE_WORKLOAD_EMAIL`;
- `SUPABASE_WORKLOAD_PASSWORD`;
- bucket privado `raw-artifacts`.

O usuário Auth técnico é autorizado por UUID somente para `SELECT` e `INSERT`
em `querido-diario/gazettes/`. O coletor rejeita `SUPABASE_SECRET_KEY` e
`SUPABASE_SERVICE_ROLE_KEY`, pois essas chaves ignoram RLS.

Não use `postgres` como login do worker em staging/produção. Provisione um login
dedicado como membro de `collector_worker`; o papel não possui `DELETE` nem
`UPDATE` nas tabelas brutas.

## Coleta diária em produção

O workflow `.github/workflows/collect-querido-diario.yml` executa diariamente,
resolve a data anterior no fuso `America/Sao_Paulo` e aceita replay manual de
até sete dias. As credenciais ficam somente no cofre do GitHub Actions; a
Vercel não executa coletores e não recebe esses segredos.

Falhas geram um artifact sanitizado de DLQ, retido por 30 dias, para replay
manual. Consulte `docs/COLLECTOR_OPERATIONS.md` para agenda, variáveis,
recuperação e limitações.
