# ADR 0069 — CGU complementa execução federal regionalizada

## Contexto

O recorte histórico do Transferegov parte de propostas cujo destino municipal
foi comprovado. Ele não representa toda a execução federal regionalizada no
Portal da Transparência. A comparação com o arquivo oficial da CGU encontrou
15 linhas para o código IBGE `2903201`, inclusive sete emendas de Carlos Tito
que não apareciam na projeção atual.

## Decisão

- Preservar integralmente o ZIP nacional de emendas da CGU em corredor privado.
- Materializar somente linhas com código IBGE exatamente igual a `2903201`.
- Manter empenhado, liquidado, pago no exercício, restos inscritos, cancelados
  e pagos em campos separados.
- Calcular total pago apenas em SQL determinístico como `pago + restos pagos`.
- Publicar esta série separadamente como execução federal regionalizada para
  Barreiras; não chamá-la automaticamente de repasse à Prefeitura.
- Separar rankings de pessoas e autorias coletivas.
- Manter ano fiscal visível. O ano de transição pode aparecer na listagem mesmo
  quando um ranking por legislatura o exclui por falta de data mais precisa.

## Consequências

- A emenda `202340720005` e registros anteriores passam a ter uma fonte
  verificável independente do recorte por propostas do Transferegov.
- Uma mesma emenda em fontes diferentes não deve ser somada duas vezes; a
  reconciliação futura usará código oficial, ano, autor e evidência.
- Ausência de anos posteriores no retrato observado significa apenas "não
  encontrado nesta fonte", nunca contribuição zero.
- O ranking descreve valores publicados e estágios de execução, não qualidade
  política, regularidade, entrega do objeto ou mérito subjetivo.
