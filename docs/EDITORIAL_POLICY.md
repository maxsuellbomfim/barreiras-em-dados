# Política editorial

## Missão editorial

Explicar registros públicos de Barreiras com linguagem clara, neutralidade,
proveniência e possibilidade de correção. O portal não é órgão de investigação,
tribunal, campanha política nem substituto da fonte oficial.

## Tipos de afirmação

| Tipo | Definição | Pode ser publicado automaticamente? |
|---|---|---|
| Fato | Campo sustentado diretamente por fonte citada | não na fase inicial |
| Inferência | Resultado lógico reprodutível a partir de fatos | não |
| Anomalia | Regra técnica detectou desvio/condição | nunca |
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

Somente `approved` pode gerar projeção pública. Publicação registra revisor,
data, versão, evidências e texto aprovado.

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

Exige revisão humana reforçada quando puder afetar honra, imagem ou expectativa
de licitude. Regras:

- duas revisões independentes para insight reputacional;
- consulta a especialista contábil/jurídico conforme o tema;
- contexto, denominador e limitações exibidos;
- tentativa documentada de obter esclarecimento quando apropriado;
- proibição de título acusatório baseado em anomalia;
- sem publicação automática, mesmo que a regra tenha alta confiança.

### Gates adicionais

| Conteúdo | Condição mínima |
|---|---|
| Sanção CEIS/CNEP/CEPIM/CEAF | identificador exato, vigência e fonte oficial |
| Relação societária | fonte cadastral, papel, data e identidade resolvida |
| Declaração eleitoral | eleição e aviso de que o valor é autodeclarado |
| Processo judicial | papel processual e situação confirmados; revisão jurídica |
| Grafo | evidência por aresta e ausência de inferência visual de culpa |
| Exportação reputacional | revisão humana, auditoria e mesmas restrições do portal |

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

O portal fornecerá formulário com:

- registro/URL contestado;
- descrição objetiva;
- fonte ou documento de suporte;
- contato e autorização de publicação;
- protocolo e estado da análise.

Contestação não altera dados automaticamente e contato pessoal não é público.

## Uso de IA

Saídas de IA são candidatas auditáveis. A interface de revisão mostra modelo,
prompt/template, versão, entradas, confiança declarada e evidência. É proibido:

- publicar texto gerado sem revisão;
- pedir ao modelo conclusão jurídica ou reputacional;
- usar o modelo para totalizar valores;
- criar citação não presente no documento;
- esconder que uma classificação foi sugerida por IA.

## Responsabilidade

A política deve ser reavaliada antes do lançamento e por ocasião de nova classe
de dado ou insight. Casos duvidosos permanecem não publicados.
