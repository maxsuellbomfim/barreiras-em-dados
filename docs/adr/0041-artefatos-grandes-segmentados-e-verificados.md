# ADR 0041 — Artefatos grandes segmentados e verificados

## Estado

Aceito em 05/08/2026.

## Contexto

Uma edição oficial do Diário com 60.599.318 bytes excedeu o limite por objeto do
Storage contratado. A coleta já havia preservado as demais edições da janela,
mas não podia concluir esse documento sem aumentar o plano ou alterar sua
representação. O acervo deve continuar imutável, verificável e legível pelos
workers existentes.

## Decisão

1. Artefatos de até 32 MiB mantêm a representação original.
2. Artefatos maiores são divididos em partes determinísticas de até 32 MiB.
3. Cada parte usa chave derivada da chave canônica, posição e SHA-256 próprios.
4. A chave canônica guarda um manifesto JSON versionado, nunca os bytes
   truncados. O manifesto usa `application/json`, tipo já autorizado pela
   allowlist do bucket privado.
5. O adaptador recompõe o conteúdo e verifica ordem, caminhos, tamanhos, hashes
   das partes e hash integral antes de entregá-lo a qualquer consumidor.
6. Replays não sobrescrevem partes ou manifestos: verificam e reutilizam o que
   já existe.
7. Objetos antigos permanecem compatíveis e são lidos sem conversão.

## Alternativas rejeitadas

- aumentar o plano como requisito: transfere uma restrição operacional para o
  orçamento e não melhora a portabilidade;
- comprimir ou alterar o PDF: muda a evidência e o hash da fonte;
- ignorar a edição grande: cria lacuna histórica silenciosa;
- armazenar somente URL externa: não preserva a prova contra alteração futura.

## Consequências

- o PostgreSQL continua registrando chave, tamanho e SHA-256 do documento
  integral;
- partes sem manifesto podem permanecer após falha e ser reutilizadas no retry;
- acesso ao bruto deve passar pelo adaptador, não por URL pública direta do
  objeto;
- uma futura troca de Storage não altera o contrato dos coletores.
