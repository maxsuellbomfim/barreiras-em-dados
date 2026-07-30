# Visão do produto

## Propósito

**Barreiras em Dados** transforma publicações dispersas da Prefeitura e da
Câmara Municipal de Barreiras (BA) em informação pública pesquisável, sem
substituir a fonte oficial e sem emitir juízos automáticos sobre pessoas.

A unidade básica do produto não é um gráfico: é uma afirmação verificável,
ligada ao registro bruto, ao documento, ao trecho sustentador, à data de coleta
e à versão do processo que a produziu.

## Problema

Os dados municipais existem em portais, PDFs, diários, APIs e sistemas com
formatos, chaves e períodos diferentes. Isso dificulta:

- acompanhar um ato ao longo do tempo;
- entender a sequência empenho → liquidação → pagamento;
- relacionar contratação, item, fornecedor, contrato e documento;
- distinguir ausência de dado, atraso da fonte e valor igual a zero;
- reproduzir uma análise e corrigir erros sem apagar o histórico.

## Públicos prioritários

- cidadãos sem conhecimento contábil;
- jornalistas e organizações de controle social;
- pesquisadores e desenvolvedores;
- servidores e órgãos públicos que precisam conferir a própria publicação;
- equipe editorial responsável por validar extrações.

## Proposta de valor municipal

O recorte exclusivo em Barreiras permite investir em profundidade: acompanhar a
semântica local, mapear secretarias e unidades, manter séries históricas,
resolver conflitos de identidade e revisar manualmente os casos relevantes.
Não tentaremos generalizar prematuramente para todos os municípios.

## Primeiro resultado público

Uma linha do tempo de nomeações e exonerações que permita filtrar por pessoa,
cargo, secretaria e período. Cada evento aprovado exibirá:

- campos extraídos e estado editorial;
- documento oficial e metadados da edição;
- trecho exato que sustenta o evento;
- fonte, URL e data de coleta;
- aviso claro quando houver correção ou conflito.

## Princípios refinados

1. Evidência antes de interface.
2. Preservar antes de transformar.
3. Ausência, indisponibilidade e zero são estados diferentes.
4. Dados normalizados são versões derivadas, não substitutos do bruto.
5. Publicação exige proveniência completa e estado editorial aprovado.
6. Cálculos financeiros usam decimal exato e código determinístico testado.
7. IA pode sugerir extração ou classificação, nunca decidir publicação.
8. Anomalia é um sinal técnico, não prova de ilícito.
9. Minimização de dados vale também para documentos originalmente públicos.
10. Metodologia, limitações e correções são parte visível do produto.

## Fora de escopo

- scores de honestidade, integridade ou corrupção;
- ranking reputacional de pessoas;
- conclusão jurídica ou acusação automática;
- reconhecimento facial;
- publicação de CPF completo ou descontos pessoais detalhados;
- comparação de preços antes de unidade, período, especificação e contexto
  estarem normalizados;
- chatbot sem citação por afirmação;
- arquitetura distribuída que não seja exigida pelo fluxo ativo.

## Métricas de sucesso

### Confiabilidade

- 100% dos registros publicados com ao menos uma evidência válida;
- 100% dos artefatos preservados com SHA-256 verificado;
- nenhuma falha de fonte contabilizada como coleta vazia bem-sucedida;
- taxa de reprocessamento idempotente sem duplicação.

### Qualidade

- precisão e revocação medidas em uma amostra anotada de atos;
- conflitos de fonte e campos incertos explicitamente quantificados;
- tempo entre coleta, revisão e publicação acompanhado por etapa.

### Utilidade pública

- cobertura histórica e atualidade por fonte;
- filtros e páginas compreensíveis em linguagem comum;
- WCAG 2.1 AA, navegação por teclado e bom desempenho em rede móvel;
- downloads e API com os mesmos estados e limitações da interface.

## Critério de lançamento

O produto não deve ser divulgado como base confiável enquanto a primeira fatia
vertical não passar pelos gates de evidência, segurança, qualidade, revisão
editorial, acessibilidade e recuperação de falhas definidos no roadmap.
