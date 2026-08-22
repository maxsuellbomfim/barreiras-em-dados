# ADR 0077 — Faixas agregadas de provento bruto

## Status

Aceita em 22 de agosto de 2026.

## Contexto

O total mensal da folha não responde quantos vínculos aparecem em valores
baixos, intermediários ou altos. Publicar linhas individuais, nomes, cargos ou
descontos não é necessário para essa resposta e ampliaria a exposição pessoal.
Também seria incorreto somar 13º à remuneração regular para classificar faixas.

## Decisão

- usar somente o componente regular, vigente e validado de cada competência;
- classificar o provento bruto declarado em seis faixas fixas: até R$ 1.500;
  R$ 1.500,01–3 mil; R$ 3.000,01–5 mil; R$ 5.000,01–10 mil;
  R$ 10.000,01–20 mil; e acima de R$ 20 mil;
- exigir que contagem e soma bruta de todas as linhas coincidam exatamente com
  o agregado oficial antes de persistir;
- descartar nomes, matrículas, CPF, cargos, lotações, descontos e líquidos
  individuais na fronteira do parser;
- persistir tabela privada imutável e publicar apenas faixa, contagem, total
  bruto, média bruta do relatório e maior bruto observado;
- chamar os valores de proventos brutos, não de salário-base nem pagamento
  bancário;
- calcular faixas, média, maior valor e percentuais por código determinístico,
  sem IA.

## Consequências

A página financeira poderá mostrar a distribuição da folha sem criar um cadastro
público individual. Competências cujo leiaute não permita reconciliar todas as
linhas ficam sem distribuição; isso significa “detalhamento indisponível”, não
zero. O maior valor é o maior provento bruto em uma linha do PDF e pode reunir
vantagens ou outros componentes previstos no relatório.
