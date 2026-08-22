# ADR 0076 — Folha agregada por regime ou vínculo

## Status

Aceita em 22 de agosto de 2026.

## Contexto

O PDF oficial da relação de servidores de julho de 2026 informa, por linha, a
classificação `Regime/Vínculo`. Publicar as linhas individuais ampliaria a
exposição de dados pessoais e não é necessário para responder quanto cada grupo
representa no custo da folha. Somar grupos sem conferir todas as linhas também
poderia omitir vínculos ou produzir totais incompatíveis com o documento.

## Decisão

- reconhecer somente oito rótulos efetivamente observados e mapeados de forma
  versionada: estatutários, cargos em comissão, processo seletivo, cedidos,
  agentes políticos, conselho tutelar, pensionistas e trabalhadores temporários;
- rejeitar o documento inteiro quando surgir rótulo ausente, desconhecido ou
  ambíguo, sem pedir à IA que escolha uma categoria;
- validar a aritmética de cada linha em memória e descartar imediatamente nome,
  matrícula, cargo, lotação e valores individuais;
- persistir somente quantidade de vínculos, proventos, descontos e líquido por
  categoria, vinculados ao agregado mensal, artefato bruto, hash e parser;
- exigir que a soma das categorias seja idêntica ao total validado do componente
  mensal antes da inserção;
- publicar a projeção do mês somente quando todos os componentes vigentes desse
  mês tiverem detalhamento compatível;
- contar vínculos somente no componente regular, embora os valores monetários
  incluam todos os processamentos mensais válidos;
- calcular percentuais em centavos por código determinístico, sem IA;
- manter a apresentação recolhida por padrão para preservar a leitura simples da
  visão mensal.

## Consequências

O cidadão poderá comparar a composição da folha sem acessar dados funcionais
individuais. “Vínculo” continua significando a relação registrada no relatório,
e não pessoa única. Leiautes históricos sem a coluna `Regime/Vínculo` permanecem
publicados no total mensal, mas não recebem uma divisão inventada: o detalhamento
fica indisponível até existir evidência oficial compatível.

## Primeira reconciliação comprovada

No PDF regular de julho de 2026, 8.184 linhas foram agrupadas em oito categorias.
Quantidade, proventos, descontos e líquido fecharam exatamente com o total geral
já publicado. A execução de produção permanece condicionada à migration, ao
workflow e à confirmação posterior da RPC pública.
