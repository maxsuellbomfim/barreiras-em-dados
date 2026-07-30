# Sistema de design

## Direção

O **Barreiras em Dados** terá uma linguagem visual inspirada nos princípios de
design da Apple: clareza, hierarquia, familiaridade, resposta imediata,
acessibilidade e atenção aos detalhes. Isso não significa copiar a marca, os
sites ou os componentes da Apple.

A sensação desejada é **calma, confiança e controle**. O portal deve ajudar o
cidadão a conferir fatos e formular perguntas melhores, não induzir indignação
ou sugerir culpa.

## Princípio central

> A evidência é o principal elemento visual.

Gráficos, números e resumos são caminhos para o documento, nunca substitutos
dele. Toda página factual deve permitir chegar à fonte, ao trecho sustentador,
à data de coleta e ao método em no máximo uma ação contextual.

## Hierarquia da informação

1. fato ou evento em linguagem simples;
2. estado da informação: publicado, corrigido, conflitante ou incompleto;
3. data, órgão e campos essenciais;
4. documento e trecho de sustentação;
5. proveniência técnica e metodologia;
6. ações secundárias, como compartilhar, exportar ou solicitar correção.

“Anomalia” e “hipótese” nunca usam o mesmo tratamento visual de um fato
documentado. Cor, ícone e texto trabalham juntos; nenhum estado depende somente
de cor.

## Padrões de página prioritários

### O que mudou

Resumo cronológico de novos atos, correções, retiradas e lacunas. Cada item
explica o tipo de mudança e abre a evidência sem perder a posição da lista.

### Linha do tempo

Filtros por pessoa, cargo, secretaria e período geram URL permanente. A
interface distingue data do ato, vigência, coleta e publicação editorial.

### Painel de evidência

No desktop, abre como painel lateral; no celular, como folha inferior ou página
dedicada. Deve conter:

- trecho sustentador com contexto suficiente;
- visualização do documento e número da página;
- fonte, URL, edição e data de coleta;
- SHA-256, versão do parser e histórico de correções;
- ação clara para abrir ou baixar o original;
- canal para contestar ou pedir correção.

O painel preserva o contexto da consulta e pode ser aberto por teclado.

### Saúde das fontes

Exibe cobertura, última coleta bem-sucedida, atraso, lacunas e falhas. “Sem
registros”, “fonte indisponível” e “ainda não coletado” são estados distintos.

### Rastro da contratação

Contratação, itens, resultado, fornecedor, contrato, aditivo e execução
financeira formam uma sequência navegável. Ausências e conflitos aparecem no
ponto exato do rastro, sem preencher lacunas por inferência silenciosa.

## Tipografia e densidade

- pilha de fontes do sistema; nenhuma fonte remota obrigatória para ler o portal;
- títulos de exibição com espaçamento óptico mais fechado e peso moderado;
- corpo com altura de linha confortável e largura de leitura limitada;
- números tabulares em valores, datas e séries comparáveis;
- tabelas densas apenas quando a tarefa exige comparação;
- linguagem direta em português, com termos técnicos explicados no contexto.

## Cor e materiais

- base neutra com alto contraste e uma cor institucional própria;
- cores semânticas reservadas para estados, não para decorar categorias;
- vermelho não significa “corrupção”; é reservado a erro, risco operacional ou
  ação destrutiva;
- materiais translúcidos podem aparecer na navegação e no painel de evidência;
- tabelas, documentos e textos longos usam superfícies sólidas;
- evitar camadas sucessivas de vidro, sombras pesadas e fundos que prejudiquem
  contraste ou desempenho.

A marca municipal, partidária ou de governo não define a paleta do produto.

## Movimento e resposta

- controles respondem visualmente ao pressionar, sem esperar a ação concluir;
- transições são curtas, interrompíveis e explicam continuidade espacial;
- o comportamento padrão não usa quique;
- movimento de gráficos não altera a percepção de valores;
- carregamento preserva a geometria para evitar saltos de layout;
- `prefers-reduced-motion` remove movimentos não essenciais;
- transparência e contraste devem ter alternativas sólidas.

## Acessibilidade

WCAG 2.1 AA é requisito mínimo:

- navegação completa por teclado e foco sempre visível;
- alvos de toque confortáveis e espaçamento que evite ativações acidentais;
- zoom e tamanhos de texto do sistema não quebram o fluxo;
- rótulos explícitos em ícones e controles;
- tabelas com cabeçalhos, legenda e alternativa linear;
- gráficos acompanhados por resumo textual e dados acessíveis;
- documento e trecho continuam utilizáveis sem animação ou transparência;
- datas, valores e siglas têm leitura compreensível por tecnologia assistiva.

## Componentes iniciais

O pacote `packages/ui` deverá começar pequeno:

- cabeçalho e navegação responsiva;
- campo de busca;
- barra de filtros com resumo dos filtros ativos;
- item de linha do tempo;
- selo de estado com texto;
- cartão de fonte;
- painel de evidência;
- indicador de cobertura da fonte;
- tabela de dados acessível;
- aviso de limitação ou conflito;
- ação de correção.

Componentes do `shadcn/ui` podem fornecer comportamento e acessibilidade, mas
receberão tokens e composição próprios. Não haverá catálogo extenso antes de
existirem telas reais.

## Tokens iniciais

Os nomes dos tokens descrevem função, não cor concreta:

- `surface-canvas`, `surface-raised`, `surface-evidence`;
- `text-primary`, `text-secondary`, `text-muted`;
- `border-subtle`, `border-strong`, `focus-ring`;
- `status-published`, `status-corrected`, `status-conflict`,
  `status-incomplete`;
- `space-1` a `space-8`;
- `radius-control`, `radius-panel`;
- `duration-immediate`, `duration-transition`;
- `shadow-navigation`, `shadow-evidence`.

Temas claro e escuro devem preservar a mesma hierarquia semântica.

## Anti-padrões

- placar, velocímetro ou termômetro de “corrupção”;
- estética policial, partidária ou de denúncia sensacionalista;
- contadores animados que dramatizam dinheiro público;
- gráficos 3D, parallax ou movimento contínuo;
- navegação escondida quando o espaço permite rótulos;
- glassmorphism em tabelas ou documentos;
- cor como única diferença entre fato, inferência e hipótese;
- cards em excesso quando lista, tabela ou linha do tempo são mais claras;
- resumo de IA sem fonte ao lado de cada afirmação.

## Validação

Antes de publicar uma nova tela:

1. testar a tarefa principal em celular e desktop;
2. verificar teclado, leitor de tela, contraste, zoom e movimento reduzido;
3. confirmar que fonte, coleta, cobertura e limitações são encontráveis;
4. testar estados vazio, indisponível, incompleto, conflitante e corrigido;
5. conferir que o design não atribui culpa ou certeza além da evidência;
6. medir desempenho em conexão móvel.
