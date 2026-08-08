# Diário Oficial integral e segmentado

Data: 8 de agosto de 2026  
Status: aprovado para planejamento

## Objetivo

O Barreiras 360 publicará o conteúdo integral de cada documento contido nas edições do Diário Oficial de Barreiras. O sistema organizará o acervo, mas não resumirá, traduzirá, reescreverá ou completará o conteúdo oficial.

O objetivo primário é permitir que o cidadão encontre e leia cada portaria, decreto, lei, edital, contrato, aviso, resolução e qualquer outro documento publicado sem precisar percorrer um PDF inteiro. A organização nunca poderá causar perda, mistura ou atribuição incorreta de texto.

## Decisões de produto

- O texto exibido será integral e proveniente do PDF oficial preservado.
- Não haverá campo de “explicação em palavras simples” neste fluxo.
- Não haverá resumo gerado por IA nem fallback determinístico apresentado como resumo.
- A classificação por tipo será apenas organizacional e derivada do título literal quando este existir.
- Se uma separação não puder ser comprovada, a edição será publicada como um bloco integral marcado como “ainda não separada”.
- Em caso de dúvida, o sistema mantém conteúdo unido. Nunca corta para produzir artificialmente dois documentos.
- Versões antigas de resumos permanecem no histórico de auditoria, mas não entram na projeção pública.

## Alternativas consideradas

### Uma página por bloco

Evita parte dos cortes, mas mistura documentos que compartilham uma página e separa documentos que continuam na página seguinte. Não atende ao objetivo.

### Separação apenas por palavras-chave

Usa expressões como `PORTARIA`, `DECRETO` e `EDITAL`. Foi rejeitada porque essas expressões aparecem em citações legais, anexos e no corpo de outros documentos. Essa abordagem já produziu títulos falsos e limites incorretos.

### Separação estrutural verificável

É a abordagem escolhida. Combina blocos e coordenadas do PDF, páginas, títulos literais, numeração, assinaturas, marcadores de encerramento, repetição de cabeçalhos e continuidade textual. A IA pode sugerir limites, mas nenhum limite sugerido é publicado sem validação determinística.

## Arquitetura

O fluxo terá cinco unidades isoladas:

1. **Preservação:** mantém PDF, resposta HTTP, URL, data da coleta, hash e metadados imutáveis.
2. **Extração de layout:** produz blocos ordenados com página, coordenadas, texto e método de extração. OCR é uma camada complementar e identificada.
3. **Detecção de limites:** propõe inícios e fins de documentos usando sinais estruturais. Não produz conteúdo novo.
4. **Validação de integridade:** comprova cobertura, ordem, ausência de sobreposição e vínculo literal com as páginas.
5. **Projeção pública:** publica somente segmentos validados ou, na ausência deles, a edição integral.

Cada unidade terá contrato e versão próprios. Trocar o extrator de PDF ou o mecanismo de sugestão não alterará o contrato público.

## Modelo de dados

Será criada uma entidade normalizada para os documentos separados, sem modificar migrations históricas.

### `raw.document_blocks`

Representa a extração de layout de uma página:

- artefato bruto;
- página;
- ordem do bloco;
- coordenadas;
- texto literal;
- hash do texto;
- método e versão do extrator;
- indicação de OCR.

### `public.gazette_documents`

Representa um documento integral validado:

- edição e artefato de origem;
- ordem dentro da edição;
- título literal, quando disponível;
- tipo organizacional opcional;
- página inicial e final;
- referências aos blocos inicial e final;
- texto integral;
- hash do texto integral;
- estado `validated` ou `edition_fallback`;
- confiança dos limites, usada internamente;
- versão do segmentador e do validador;
- data de publicação e histórico de substituição.

Nenhum registro normalizado existirá sem vínculo com o artefato bruto e suas páginas.

## Separação de documentos

Um limite candidato poderá utilizar:

- bloco visual destacado ou centralizado;
- título em caixa alta ou com tipografia distinta;
- espécie e número do ato;
- data oficial próxima ao título;
- mudança de órgão ou seção;
- assinatura e encerramento seguidos de novo título;
- continuidade sintática e visual entre páginas;
- sumário ou índice da própria edição, quando existente.

Palavras-chave isoladas nunca bastam. Uma referência a outra lei, decreto, portaria, edital ou contrato dentro do texto não cria um novo documento.

A IA, quando disponível, receberá blocos com suas posições e poderá sugerir limites. A resposta será tratada somente como hipótese. O código continuará responsável por aceitar ou rejeitar cada limite.

## Validação de integridade

Uma edição só será publicada como segmentada quando todos os critérios forem satisfeitos:

- todos os blocos de conteúdo pertencem exatamente a um documento;
- não existem lacunas nem sobreposições;
- a ordem dos blocos e páginas é preservada;
- cada texto publicado corresponde literalmente aos blocos de origem;
- continuações entre páginas permanecem juntas;
- nenhum limite termina no meio de palavra, linha estrutural ou parágrafo;
- cabeçalhos e rodapés removidos são identificados como elementos repetitivos e permanecem recuperáveis na origem;
- o hash do conjunto ordenado de blocos é conferido;
- a quantidade de páginas e o intervalo de cada documento são registrados.

Se qualquer critério falhar, nenhum segmento daquela versão é publicado. A projeção usa `edition_fallback` e mostra o texto integral da edição.

## Interface pública

A página deixa de se chamar “Diário Oficial traduzido” e passa a apresentar o “Diário Oficial organizado”.

Cada edição mostrará:

- número, data e indicação de edição ordinária ou extra, quando a fonte informar;
- quantidade de documentos separados e estado da separação;
- busca dentro da edição;
- lista na ordem original.

Cada documento mostrará inicialmente:

- título literal;
- tipo organizacional, quando inequívoco;
- páginas abrangidas;
- botão para abrir o conteúdo integral;
- botão para abrir o PDF oficial na página correspondente, quando tecnicamente possível.

Ao expandir, o usuário verá todo o texto do documento, sem limite artificial de caracteres. Documentos longos poderão usar navegação interna e carregamento progressivo, mas o conteúdo não será resumido.

Quando a edição ainda não estiver segmentada, a interface informará isso claramente e oferecerá o texto integral e o PDF, sem aparentar que o processamento terminou.

## Correções e versões anteriores

Resumos e segmentos defeituosos não serão apagados. Uma decisão `withdrawn` os retira da projeção pública e registra a justificativa. Uma nova separação cria nova versão ligada à anterior.

O sistema nunca reutilizará silenciosamente um resultado produzido por versão antiga do segmentador ou validador.

## Testes e critérios de aceitação

- A concatenação ordenada dos documentos corresponde ao conteúdo canônico da edição, descontados somente elementos repetitivos registrados.
- Nenhum caractere pertencente ao conteúdo oficial é perdido.
- Nenhum bloco aparece em dois documentos.
- Um documento que atravessa páginas permanece único.
- Uma citação a outro ato não inicia novo documento.
- Uma edição ambígua aparece integralmente, sem falsa segmentação.
- O texto público não contém resumo, paráfrase ou conteúdo gerado.
- O título público é literal ou explicitamente ausente.
- Cada documento informa páginas, artefato, hash e versões do processamento.
- Fixtures reais incluirão edições com atos de pessoal, contratos, editais, decretos, anexos, tabelas e documentos iniciados ou encerrados no meio da página.
- A edição 4706 será uma fixture de regressão, mas os testes serão gerais e não codificarão correções exclusivas para ela.
- O portal será verificado em telas móveis e desktop, incluindo documentos extensos.

## Migração e implantação

1. Manter os resumos antigos fora da projeção pública.
2. Criar tabelas e contratos do novo fluxo.
3. Extrair blocos das edições já preservadas.
4. Executar o segmentador em modo de avaliação, sem publicação.
5. Validar fixtures reais e comparar automaticamente cobertura e hashes.
6. Publicar inicialmente uma edição aprovada pelo novo validador.
7. Reprocessar o acervo em lotes idempotentes.
8. Substituir a interface antiga após comprovar o fallback integral.

## Fora do escopo desta entrega

- resumo ou tradução por IA;
- interpretação jurídica;
- inferência sobre pessoas ou organizações;
- cálculo financeiro a partir do texto do Diário;
- classificação reputacional;
- remoção dos PDFs e dados históricos já preservados.

