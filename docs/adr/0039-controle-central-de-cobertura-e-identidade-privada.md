# ADR 0039 — Controle central de cobertura e identidade privada

## Estado

Aceito em 05/08/2026.

## Contexto

Execuções que falhavam antes da primeira persistência podiam existir somente
no GitHub Actions. Também faltava um contrato uniforme para distinguir fonte
vazia de janela não coletada. A reconciliação política precisa de identificador
forte quando uma fonte oficial o publica, sem transformar CPF em dado público.

## Decisão

1. Cada janela controlada cria `collection_runs` antes do HTTP.
2. Cobertura e falhas usam `collection_partitions` e `collection_failures`.
3. CPF fica em `private.person_identifiers`, cifrado por AES-256-GCM e
   comparado por HMAC-SHA-256 com chave distinta.
4. `collector_worker` não acessa identificadores; somente `identity_worker`
   recebe `SELECT` e `INSERT`.
5. Nenhuma aplicação pública ou painel comum recebe CPF completo.

## Consequências

- backfills podem provar cobertura, vazio e bloqueio sem inferência;
- falhas passam a ser consultáveis e reproduzíveis fora do provedor de CI;
- identidade forte não amplia a superfície do Data API;
- cada coletor existente precisará migrar para o novo contrato em uma entrega
  testável, começando pelo Diário direto.
