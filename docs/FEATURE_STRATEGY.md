# Estratégia de funcionalidades

## Objetivo de impacto

O portal deve criar pressão pública por quatro meios legítimos:

1. tornar atos oficiais fáceis de encontrar e entender;
2. impedir que documentos e versões desapareçam sem registro;
3. permitir que qualquer afirmação seja conferida na fonte;
4. reduzir o custo para imprensa, conselhos e cidadãos fazerem perguntas.

O produto não afirma quem é honesto ou corrupto. Ele mostra, com método
reproduzível, o que aconteceu, quanto custou, quem participou, o que mudou e
quais informações continuam ausentes ou conflitantes.

Mensagem editorial sugerida:

> A administração muda; os documentos e o histórico permanecem.

## Funcionalidades prioritárias

### P0 — primeiro fluxo vertical

- **O que mudou:** nomeações e exonerações novas, corrigidas ou retiradas desde
  a última coleta.
- **Linha do tempo pesquisável:** pessoa, cargo, secretaria e período, sempre
  com estado de revisão visível.
- **Gaveta de evidência:** documento original, trecho, página, URL, data da
  coleta, hash e versão do parser.
- **Cartão de fonte compartilhável:** resumo factual para WhatsApp e redes,
  contendo link permanente para a evidência, sem adjetivação.
- **Saúde das fontes:** última coleta bem-sucedida, lacunas de datas, erros,
  documentos indisponíveis e atraso da fonte.
- **Histórico de correções:** versão anterior, versão vigente, motivo, data e
  responsável pela revisão.
- **Glossário em linguagem simples:** “nomeação”, “exoneração”, “empenho”,
  “liquidação” e outros termos, com metodologia pública.

### P1 — PNCP e rastro do dinheiro

- **Rastro da contratação:** contratação → item → proposta/resultado →
  fornecedor → contrato → aditivo → empenho → liquidação → pagamento.
- **Página de fornecedor:** contratos e valores documentados, vínculos de
  fonte confirmada e nomes anteriores; sem produzir nota reputacional.
- **Linha do tempo do contrato:** valor inicial, aditivos, prazo e documentos.
- **Painel de obras:** localização pública, cronograma, medições, aditivos,
  pagamentos e fotos oficiais preservadas.
- **Registro de conflitos entre fontes:** divergência exibida sem escolher
  silenciosamente um “vencedor”.
- **Downloads e API:** CSV/JSON, dicionário de dados, versão e filtros
  reproduzíveis.

### P1 — participação cidadã

- **Alertas por filtro:** RSS primeiro; depois e-mail e web push com
  consentimento e descadastro.
- **Pergunte com base nos dados:** gerar um rascunho de pedido LAI com fontes e
  campos ausentes. O cidadão revisa e envia pelo canal oficial; o sistema não
  protocola automaticamente.
- **Acompanhar protocolos voluntários:** o cidadão pode registrar número,
  prazo e resposta, removendo dados pessoais antes da publicação.
- **Agenda de concursos:** editais, retificações, convocações e prazo de
  validade.

### P2 — controle social ampliado

- atos, pautas, votações e presença da Câmara, conforme fontes disponíveis;
- comparação entre exercícios e gestões somente com períodos, deflatores e
  categorias equivalentes;
- comparação de preços somente após normalização de item, unidade, quantidade,
  qualidade, local e data;
- sinais de anomalia aprovados editorialmente, acompanhados de contexto,
  limitações e linguagem explícita de que não são prova de irregularidade.

## Experiência transversal obrigatória

Toda página factual deve responder:

- qual é a fonte;
- quando foi coletada;
- qual período está coberto;
- o que está ausente;
- se houve transformação ou inferência;
- como reproduzir;
- como contestar ou pedir correção.

Filtros devem gerar URLs permanentes. Resultados extensos usam paginação por
cursor. Datas, moeda e estados de revisão não podem depender apenas de cor.

## Funcionalidades que não entram no produto

- placar de honestidade, “suspeitômetro” ou ranking de pessoas;
- contagem de anomalias como indicador de corrupção;
- mural aberto de acusações;
- publicação automática de texto gerado por IA;
- perfilamento político, reconhecimento facial ou exposição de CPF;
- comparação de preços sem equivalência comprovada;
- interpretação de silêncio administrativo como culpa.

## Métricas de produto

Medir utilidade e qualidade, não engajamento indignado:

- percentual de registros publicados com evidência primária;
- cobertura temporal por fonte;
- tempo entre publicação oficial, coleta e revisão;
- taxa de extrações corrigidas na revisão;
- conflitos de fonte abertos e resolvidos;
- correções solicitadas, aceitas e tempo de resposta;
- downloads, consultas reproduzíveis e acessos ao documento original;
- disponibilidade e desempenho do portal.
