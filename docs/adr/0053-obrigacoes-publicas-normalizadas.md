# ADR 0053 — Obrigações públicas normalizadas

## Status

Aceito

## Contexto

O portal já preserva balancetes, contas anuais, RREO e RGF como documentos-base.
Esses artefatos ajudam a localizar empréstimos, precatórios, restos a pagar e
outros passivos, mas não são comparáveis enquanto permanecem apenas como PDFs.
Também não é correto somar linhas isoladas, períodos distintos ou retificações
e apresentar o resultado como “dívida total”.

## Decisão

1. Criar `finance.public_obligations` para linhas normalizadas de obrigações,
   sempre vinculadas a `raw.raw_records` e ao órgão público responsável.
2. Separar saldo inicial, acréscimos, reduções, pagamentos e saldo final, usando
   `numeric(20,2)` e moeda BRL.
3. Distinguir empréstimos, precatórios, contas a pagar, restos a pagar
   processados e não processados, obrigações previdenciárias e ordens judiciais.
4. Preservar versões por órgão e chave de obrigação e encadear retificações por
   `supersedes_id`; uma versão não pode substituir obrigação de outro órgão, e
   UPDATE e DELETE são rejeitados.
5. Expor pela RPC `api.get_public_obligations` somente registros `validated` ou
   `reconciled`, com URL, SHA-256 e instante de coleta da fonte.
6. Não expor uma coluna ou função de “total da dívida”. A consolidação só poderá
   existir depois de reconciliar competência, natureza, versão e fontes.

## Segurança e governança

- RLS é habilitada e forçada.
- `anon` e `authenticated` não leem a tabela diretamente.
- O worker de coleta recebe apenas SELECT e INSERT; não pode alterar histórico.
- A RPC usa `security definer`, `search_path` vazio, tipos em lista fechada e
  limite de página entre 1 e 200.
- Registros extraídos, conflitantes, rejeitados ou substituídos não aparecem na
  projeção pública.

## Consequências

- O projeto passa a ter um contrato verificável para obrigações municipais.
- Ausência de linha reconciliada não significa dívida zero.
- O próximo passo é implementar um normalizador determinístico para uma família
  documental por vez, começando por balancetes, e confrontar a mesma obrigação
  com SICONFI e TCM-BA antes de qualquer consolidação pública.
