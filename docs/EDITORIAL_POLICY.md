# Política editorial

## Missão editorial

Explicar registros públicos de Barreiras com linguagem clara, neutralidade,
proveniência e possibilidade de correção. O portal não é órgão de investigação,
tribunal, campanha política nem substituto da fonte oficial.

## Tipos de afirmação

| Tipo | Definição | Pode ser publicado automaticamente? |
|---|---|---|
| Fato | Campo sustentado diretamente por fonte citada | sim, conferido por código (ADR 0012) |
| Inferência | Resultado lógico reprodutível a partir de fatos | sim, com regra versionada e revisão automatizada |
| Indício (anomalia) | Regra técnica detectou desvio/condição que merece apuração | sim, com revisão automatizada registrada (ADR 0099) |
| Hipótese | Explicação possível ainda não comprovada | nunca |

O tipo deve existir nos dados e na apresentação. Linguagem e design não podem
fazer uma anomalia parecer fato ou uma hipótese parecer conclusão.

## Estados editoriais

`draft` → `needs_review` → `approved` → `published`

Saídas alternativas:

- `rejected`;
- `needs_more_evidence`;
- `conflicted`;
- `superseded`;
- `retracted`.

Somente `approved` pode gerar projeção pública. Publicação registra revisor
(pessoa ou agente automatizado, com modelo e versão do roteiro), data,
versão, evidências e texto aprovado.

## Critérios para aprovar um ato

- fonte e documento verificáveis;
- artefato com hash conferido;
- pessoa, tipo do ato, cargo/órgão e data validados;
- trecho sustentador suficiente;
- incerteza e vigência não inventadas;
- conflito relevante resolvido ou visivelmente declarado;
- nenhum dado pessoal excessivo na projeção;
- redação factual, sem adjetivo ou insinuação.

Quando o documento não declarar vigência, o sistema não deve assumir que ela é
igual à data da publicação.

## Conteúdo reputacional

Pode afetar honra, imagem ou expectativa de licitude, por isso passa por
revisão automatizada registrada em duas camadas (ADR 0099):

- conferência por código contra o documento oficial preservado;
- conferência por agente de IA, que procura erro de dado e explicação lícita
  comum e pode vetar;
- contexto, denominador, limite de cobertura e explicações lícitas comuns
  exibidos junto do indício;
- rótulo "Conferido automaticamente — sem revisão humana";
- proibição de título, texto ou ordenação que afirme ou insinue crime,
  fraude, corrupção, desvio ou superfaturamento de pessoa ou empresa
  identificada. O vocabulário é "indício", "alerta", "merece apuração".

### Gates adicionais

| Conteúdo | Condição mínima |
|---|---|
| Sanção CEIS/CNEP/CEPIM/CEAF | identificador exato, vigência e fonte oficial |
| Relação societária | fonte cadastral, papel, data e identidade resolvida |
| Declaração eleitoral | eleição e aviso de que o valor é autodeclarado |
| Processo judicial | papel processual e situação confirmados; revisão jurídica |
| Grafo | evidência por aresta e ausência de inferência visual de culpa |
| Exportação reputacional | revisão automatizada, auditoria e mesmas restrições do portal |

DataJud não será usado para busca automática por nome com o contrato público
atual. Seu schema documentado não oferece partes e seus termos exigem avaliação
jurídica adicional. O módulo fica bloqueado até o gate registrado no
[ADR 0009](adr/0009-territorial-observatory-and-reputational-boundary.md).

## Neutralidade

- mesma metodologia para Prefeitura, Câmara, gestões, partidos e fornecedores;
- filtros e ordenações não sugerem culpa;
- valor alto não é descrito como desperdício;
- dispensa ou inexigibilidade não é descrita como irregular por si;
- nomeação, exoneração e aditivo são atos administrativos, sem valência
  editorial automática.
- receber emenda, ter contrato, integrar sociedade ou aparecer no mesmo grafo
  não indica favorecimento ou coordenação;
- processo judicial não será descrito como condenação;
- desempenho de secretaria será descrito por atos, metas e execução
  verificáveis, não por nota editorial de “utilidade”.

## Correções

Correções não apagam o histórico:

1. suspender a projeção se houver risco material;
2. preservar evidência e versão anterior;
3. criar revisão e versão corrigida;
4. publicar nota de correção proporcional;
5. atualizar downloads/API sem ocultar a supersessão;
6. notificar quem solicitou quando cabível.

## Direito de resposta e contestação

O portal fornece formulário anônimo, sem login, com:

- registro/URL contestado;
- descrição objetiva;
- fonte ou documento de suporte (opcional);
- contato opcional, nunca público;
- protocolo e estado da análise.

Cada contestação dispara nova conferência automatizada. Se a evidência não
se sustentar, o item é retirado por nova versão, com nota de correção; o
histórico é preservado.

## Uso de IA

A IA atua como revisora automatizada (ADR 0099): confere casos contra o
documento oficial e decide aprovar, rejeitar ou pedir mais evidência. Cada
decisão registra modelo, versão do roteiro, entradas e evidência. É proibido:

- publicar o que a conferência por código não validou;
- usar o modelo para totalizar valores;
- pedir ao modelo conclusão sobre culpa, crime ou intenção;
- criar citação não presente no documento;
- esconder que uma classificação ou revisão foi feita por IA.

## Responsabilidade

A política deve ser reavaliada antes do lançamento e por ocasião de nova classe
de dado ou insight. Casos que a revisão automatizada marcar como duvidosos
(`needs_more_evidence`) permanecem não publicados.
