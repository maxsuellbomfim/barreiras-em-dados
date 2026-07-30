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

## Persistência da primeira janela

Instale os extras fixados de PostgreSQL e Storage em um ambiente virtual e
preencha somente variáveis server-side:

```powershell
python -m pip install -e ".[postgres,storage]"
$env:PYTHONPATH='workers/collectors/src'
python -m barreiras_collectors.commands.collect_querido_diario `
  --since 2026-07-24 `
  --until 2026-07-30
```

O comando exige uma janela de no máximo sete dias. Ele salva primeiro a resposta
JSON em `raw-artifacts`, restaura e confere o SHA-256, e só então registra a
execução, o artefato e os registros no PostgreSQL. Repetir a mesma janela reutiliza
o objeto e não duplica registros.

Não use `postgres` como login do worker em staging/produção. Provisione um login
dedicado como membro de `collector_worker`; o papel não possui `DELETE` nem
`UPDATE` nas tabelas brutas.
