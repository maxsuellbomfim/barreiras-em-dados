# Avaliacao de ferramentas para documentos e fontes dinamicas

Data: 2026-08-02

## Resumo executivo

As duas ferramentas podem ser uteis, mas em lugares diferentes:

- `firecrawl/pdf-inspector`: recomendada como adaptador experimental do worker
  de processamento de documentos;
- `h4ckf0r0day/obscura`: nao entra no caminho principal agora; pode ser um
  fallback isolado para paginas publicas que exigem JavaScript.

## pdf-inspector

O projeto e uma biblioteca Rust local para classificar PDFs como textuais,
escaneados, baseados em imagem ou mistos, extrair texto com posicao e montar
Markdown com tabelas e ordem de leitura. Possui bindings para Python e Node,
nao depende de servico externo e usa MIT.

Encaixe no Barreiras em Dados:

1. classificar cada PDF antes de chamar OCR;
2. extrair localmente PDFs textuais de diarios, licitacoes e contratos;
3. guardar tipo, confianca, paginas e versao do parser como metadados;
4. encaminhar somente paginas sem texto para OCR;
5. manter o PDF original como evidencia imutavel.

Dificuldade estimada: media. O risco principal e a compilacao Rust/PyO3 no
CI e a necessidade de fixtures reais de Barreiras. A adocao deve ser por
interface, com fallback para o processador atual e benchmark antes de trocar
o caminho de producao.

## Obscura

O projeto e um navegador headless em Rust, com V8, CDP e compatibilidade com
Puppeteer/Playwright. Ele pode renderizar JavaScript, aguardar rede ociosa e
expor automacao via CLI ou MCP. A licenca informada no repositorio e Apache 2.0.

Encaixe possivel:

- fallback para portais municipais que entregam dados apenas apos JavaScript;
- ambiente separado para descobrir endpoints publicos e validar layouts;
- coletor dedicado quando HTTP simples e Playwright convencional nao forem
  suficientes.

Dificuldade estimada: alta. A compilacao envolve Rust/V8; a imagem Docker,
CDP, consumo de memoria, atualizacoes e testes de compatibilidade adicionam
operacao. O portal da Camara hoje possui API publica funcional, portanto
Obscura nao melhora o caminho atual.

## Decisao

1. Fazer um prototipo de `pdf-inspector` no worker de documentos, sem alterar
   ainda o parser oficial.
2. Registrar Obscura como ferramenta de contingencia, nao como dependencia do
   frontend ou dos coletores de API.
3. Antes de adotar qualquer uma em producao, exigir fixture, hash, teste de
   replay, limite de recursos e verificacao de licenca.
