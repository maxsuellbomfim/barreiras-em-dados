# ADR 0092 — Dívida consolidada declarada no RGF

## Status

Aceita em 30/09/2026 pelo titular ("pode seguir com a dívida da prefeitura").

## Contexto

O ADR 0053 proíbe a plataforma de somar obrigações e chamar o resultado de
"dívida total" antes de reconciliar competência, natureza e fontes. Por isso a
página de Finanças mostrava "Dívida registrada: fontes em integração". Mas o
próprio Município já declara, a cada quadrimestre, a Dívida Consolidada, as
deduções e a Dívida Consolidada Líquida no Relatório de Gestão Fiscal
(RGF-Anexo 02, LRF art. 55), publicado pelo Tesouro Nacional no SICONFI.

## Decisão

1. Coletar o RGF-Anexo 02 do Poder Executivo de Barreiras (quadrimestral,
   desde 2019) pela API oficial do SICONFI, preservando cada página JSON com
   SHA-256 no corredor privado `siconfi/rgf/` e cada linha como
   `siconfi_rgf_annex2_line`, com contrato estrito (exercício, período,
   anexo, poder e esfera conferidos).
2. Publicar por `api.get_public_debt_statements()` os valores **literais** do
   demonstrativo, na coluna acumulada do próprio quadrimestre: Dívida
   Consolidada, deduções, Dívida Consolidada Líquida, receita corrente líquida
   ajustada, percentual e limites, mais a composição completa na ordem da
   fonte. Retificação coletada depois substitui a anterior.
3. Nenhuma soma é feita pela plataforma: o total é o que o Município declarou.
   A regra do ADR 0053 continua valendo para linhas de obrigação extraídas de
   outros documentos.
4. Conta ausente fica nula ("não informado na fonte"), nunca zero; quadrimestre
   ainda não publicado não aparece como dívida zero.

## Consequências

- A pergunta "quanto a Prefeitura deve" passa a ter resposta oficial e
  verificável, com série histórica.
- O número é declaratório: erros do demonstrativo são do declarante; o portal
  mostra a fonte e o hash para quem quiser conferir.
