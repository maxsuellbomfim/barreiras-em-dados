# ADR 0082 — Separar a base legal municipal da DCA

## Status

Aceito; corrige a classificação conceitual dos ADRs 0052 e 0053.

## Contexto

O recurso de origem chamado `pdc-contas-anuais` sugeria, pelo identificador,
uma série de demonstrativos anuais. A auditoria da fonte e do acervo bruto em
1º de setembro de 2026 encontrou seis registros oficiais únicos: quatro
fundamentos constitucionais ou da LRF e duas leis municipais sobre controle
interno. Nenhum dos registros é uma demonstração anual de receitas e despesas.

Usar esses documentos para confirmar, contradizer ou completar a DCA criaria
uma comparação falsa entre objetos diferentes.

## Decisão

1. Preservar o identificador técnico da fonte para não quebrar linhagem nem
   reescrever registros históricos.
2. Apresentar a série ao cidadão como legislação de controle e prestação de
   contas, em seção separada.
3. Excluir essa série da classificação de documentos-base de dívida e de
   documentos mensais de execução.
4. Manter a DCA do Tesouro como fonte dos demonstrativos anuais comparáveis.
5. Não inferir valores, cobertura anual ou divergência financeira a partir da
   base legal.
6. Indexar separadamente a seleção dos registros financeiros e o vínculo entre
   catálogo e documento preservado, sem alterar a identidade dos artefatos.

## Evidência operacional

A consulta anterior percorreu cerca de 164 mil registros brutos para selecionar
um item e 1.474 artefatos do endpoint para procurar seu documento. Os novos
índices seguem os mesmos predicados determinísticos usados pela projeção
pública: família documental, chave oficial, endpoint e URL da fonte.

## Consequências

- O portal deixa de chamar legislação de demonstrativo anual.
- A DCA e a fonte municipal permanecem auditáveis, mas conceitualmente separadas.
- Ausência de um demonstrativo anual não é mascarada pela existência de uma lei.
- A consulta pública deixa de depender de varreduras integrais do acervo bruto.
