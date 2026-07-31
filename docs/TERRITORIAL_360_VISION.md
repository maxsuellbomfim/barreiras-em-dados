# Visão territorial 360

## Objetivo

Transformar o **Barreiras em Dados** em um observatório territorial que permita
seguir o caminho de uma decisão ou de um recurso público entre Município,
Estado e União, sem perder o foco geográfico em Barreiras e sem converter
relações públicas em acusações.

A expansão é um destino de produto, não autorização para implementar todos os
conectores simultaneamente. O primeiro fluxo do Querido Diário continua sendo o
gate de confiabilidade.

## Mapa do produto

### 1. Barreiras hoje

- receita registrada no dia, no mês e no exercício;
- composição por natureza, origem e fonte de recurso;
- horário da última atualização e cobertura da fonte;
- correções e retificações visíveis;
- distinção entre previsto, lançado, arrecadado e recolhido, quando a fonte
  disponibilizar esses estágios;
- aviso de que valor registrado não representa necessariamente saldo bancário
  disponível.

O indicador diário só será publicado quando data contábil, fuso, periodicidade,
estornos e retificações estiverem modelados. A página deve permitir chegar da
soma às linhas de origem.

### 2. Secretarias e órgãos

Cada unidade poderá ter uma página que reúna:

- atos publicados;
- orçamento autorizado e execução;
- contratações, contratos, aditivos e pagamentos;
- obras, etapas e medições;
- metas e indicadores presentes em PPA, LDO, LOA, planos setoriais e relatórios
  oficiais;
- concursos, nomeações, exonerações e estrutura de cargos;
- lacunas e atraso das fontes.

A interface usará “entregas, atos e execução verificáveis”. Não haverá score de
“utilidade”, produtividade ou eficiência sem metodologia específica,
comparabilidade e revisão especializada.

Para a Procuradoria, entram apenas atos e documentos oficialmente publicados ou
legalmente obtidos. Pareceres internos, estratégias processuais, comunicações
protegidas e dados pessoais não se tornam publicáveis apenas por terem sido
coletados.

### 3. Recursos que chegam a Barreiras

Uma página “De onde veio o dinheiro” separará:

- receitas próprias municipais;
- transferências constitucionais e legais;
- transferências fundo a fundo;
- convênios e instrumentos voluntários;
- transferências especiais;
- programas e obras estaduais ou federais;
- emendas parlamentares.

Para cada fluxo, preservar:

- concedente, recebedor e beneficiário final quando documentado;
- autor da emenda, quando aplicável;
- programa, instrumento, objeto e localidade;
- valor proposto, autorizado, empenhado, transferido/pago e executado;
- datas e histórico de alteração;
- documento e linha de origem.

Valores de estágios diferentes nunca serão somados como se fossem o mesmo fato.
“Emenda anunciada”, “emenda autorizada” e “recurso pago” são estados distintos.
O vínculo com uma despesa municipal só será criado por chaves determinísticas ou
por reconciliação humana explicitamente identificada.

### 4. Representantes acompanhados

O módulo reunirá, conforme disponibilidade oficial:

- mandatos e histórico;
- comissões e órgãos legislativos;
- proposições, relatorias e requerimentos;
- votações nominais;
- presença, agenda e discursos, com as limitações da fonte;
- despesas parlamentares;
- emendas destinadas a Barreiras e seus estágios;
- declarações de bens eleitorais por eleição.

O conjunto “de Barreiras” não será decidido por reputação ou afinidade. Cada
relação territorial terá um tipo explícito, período e evidência:

- cargo municipal eleito;
- candidatura pelo Município em eleição municipal;
- nascimento ou domicílio declarado em registro oficial;
- escritório oficial no Município;
- emenda, proposição, evento ou atuação que mencione Barreiras;
- outro vínculo aprovado editorialmente e documentado.

Votação recebida em Barreiras não prova representação exclusiva do Município.
Deputados estaduais e federais representam circunscrições mais amplas.

### 5. Registros oficiais e sanções

O nome público recomendado é **Registros oficiais e sanções**, não “alertas
judiciais” ou “ficha de suspeitas”.

#### CGU

CEIS, CNEP, CEPIM, CEAF e acordos de leniência podem alimentar registros
factuais. Uma sanção deve exibir sancionado, identificador permitido, órgão
sancionador, fundamento informado, início, fim, abrangência, situação, data da
coleta e fonte. Sanção de empresa não implica automaticamente responsabilidade
de sócios, administradores, contratantes ou agentes públicos.

Conciliação automática exige CNPJ exato. Correspondência apenas por nome gera
candidato interno e nunca publicação.

#### DataJud

A API Pública do DataJud documenta metadados de capa e movimentações, mas seu
schema público não inclui nomes das partes. Portanto, ela **não oferece,
isoladamente, busca confiável de processos por político**.

Além disso, o termo de uso vigente:

- limita o uso a finalidades legais, não comerciais e autorizadas;
- veda coleta de informações pessoais de terceiros;
- impõe condições para tratamento e compartilhamento de dados pessoais;
- responsabiliza o usuário por interpretações;
- exige ciência ao CNJ sobre material derivado disponibilizado ao público.

O conector poderá ser estudado para acompanhamento por número de processo,
classe, assunto, órgão julgador e município. Qualquer associação a uma pessoa
fica bloqueada até parecer de profissional jurídico qualificado, esclarecimento
formal do CNJ e desenho compatível com o termo. Processo, polo processual,
decisão, trânsito em julgado e sanção são fatos diferentes.

### 6. Declarações de bens eleitorais

O nome recomendado é **Declarações de bens eleitorais**, não “dossiê de
patrimônio”.

Cada conjunto pertence a uma eleição e representa o que foi declarado à Justiça
Eleitoral naquele momento. Não equivale a patrimônio líquido atual, avaliação
de mercado ou prova de evolução patrimonial ilícita. A página mostrará:

- eleição, cargo, candidatura e identificador TSE;
- categoria, descrição e valor declarado;
- correções do conjunto de origem;
- comparação nominal e real apenas quando categorias, moeda, período e
  metodologia forem compatíveis;
- limitações visíveis junto ao total.

Não haverá score automático de enriquecimento nem conclusão sobre omissão.

### 7. Rede de vínculos documentados

O nome recomendado é **Rede de vínculos públicos**, não “malha de empresas
suspeitas”. O React Flow pode ser usado como camada de visualização, mantendo os
dados no PostgreSQL inicialmente.

Cada nó e aresta deve ter:

- tipo e identificador público;
- fonte, data de observação e período de validade;
- evidência acessível;
- método de vinculação (`exact_id`, `reviewed`, `name_candidate`);
- nível de confiança de identidade;
- estado editorial;
- limitações e eventual conflito.

Tipos de aresta iniciais: sócio/administrador declarado, fornecedor de contrato,
autor de emenda, beneficiário de transferência, ocupante de cargo e parte de um
ato oficial. A interface separa vínculo documentado, inferência e hipótese por
rótulo textual, não somente por cor.

O grafo não sugere proximidade moral, coordenação ou benefício. Busca por nome
não cria aresta pública; homônimos permanecem candidatos de reconciliação.

### 8. Exportação de recortes verificáveis

PDF, DOCX e XLSX poderão ser gerados para jornalismo, pesquisa e controle
social. O nome recomendado é **Exportar recorte com evidências**.

Todo arquivo conterá:

- filtros e instante do recorte;
- versão do dataset, método e software;
- fonte por afirmação ou linha;
- notas de cobertura e limitações;
- hash do arquivo e identificador de auditoria;
- aviso de que relações e anomalias não são conclusões jurídicas.

Exportações que reúnam conteúdo reputacional serão autenticadas, limitadas,
auditadas e submetidas a revisão humana antes de liberação. Uma exportação nunca
inclui dados que a projeção pública não poderia exibir.

## Inteligência artificial

IA será um componente assistivo, independente do provedor:

- classificar documentos e encaminhá-los à fila correta;
- propor extrações estruturadas validadas por JSON Schema/Pydantic;
- sugerir descrição em linguagem simples com citação por afirmação;
- apontar possíveis correspondências de identidade para revisão;
- resumir diferenças entre versões para o editor.

É proibido usar IA para:

- somar ou reconciliar valores financeiros;
- decidir se duas pessoas são a mesma;
- concluir improbidade, corrupção, fraude ou enriquecimento;
- criar aresta pública no grafo;
- publicar sem revisão;
- responder sem fonte recuperável.

Cada execução registra provedor, modelo, versão, template do prompt, hash da
entrada, parâmetros, saída, custo e decisão humana. Chaves ficam somente em
secrets do servidor/worker; nunca no browser, Git, documento ou chat. Antes de
enviar conteúdo a um provedor, aplicar minimização de dados e revisar retenção,
treinamento, localização e suboperadores.

## Entidades futuras candidatas

Não entram na migration fundamental antes da descoberta e dos contratos das
fontes:

- `territorial_relationships`;
- `public_mandates`;
- `political_candidacies`;
- `legislative_activities`;
- `legislative_votes`;
- `parliamentary_expenses`;
- `intergovernmental_transfers`;
- `parliamentary_amendments`;
- `amendment_financial_events`;
- `electoral_asset_declarations`;
- `electoral_assets`;
- `official_case_references`;
- `sanctions`;
- `legal_entities`;
- `corporate_relationships`;
- `relationship_assertions`;
- `export_jobs` e `export_artifacts`.

Toda entidade normalizada manterá origem bruta e versão. Relações terão
proveniência própria; não basta que os dois nós tenham fonte.

## Ferramentas recomendadas quando houver necessidade

- React Flow para visualização do grafo;
- PostgreSQL com tabelas de nós/arestas e consultas recursivas inicialmente;
- PyMuPDF, OCRmyPDF e Tesseract para documentos, em sandbox;
- OpenTelemetry e Sentry para rastreabilidade e erros;
- Playwright ou renderização server-side para PDF;
- `python-docx` e `openpyxl` para DOCX/XLSX;
- gateway de IA com allowlist de modelos, orçamento e logs, sem acoplar o
  domínio a um único fornecedor.

Não adotar banco de grafos, orquestrador pesado, vector database ou ML complexo
antes de consultas reais demonstrarem a necessidade.

## Ordem mínima de entrega

1. estabilizar a coleta preservada do Querido Diário;
2. publicar atos aprovados com evidência;
3. integrar PNCP e contratações locais;
4. publicar execução orçamentária e receitas com reconciliação;
5. construir “recursos que chegam a Barreiras”;
6. acompanhar representantes e atividade legislativa;
7. integrar sanções por identificador exato;
8. liberar declarações eleitorais e rede societária documentada;
9. avaliar DataJud somente após os gates jurídicos;
10. liberar exportações reputacionais somente após revisão e auditoria.

## Dependências do responsável pelo projeto

Não há credencial nova necessária para documentar ou prototipar esta visão.
Antes de cada integração, serão solicitados apenas os acessos indispensáveis:

- token da API do Portal da Transparência/CGU, criado pelo responsável;
- chaves de provedores de IA escolhidos, inseridas diretamente no secret
  manager;
- eventual contato/anuência do CNJ;
- revisão de advogado com experiência em liberdade de expressão, imprensa,
  LGPD e responsabilidade civil;
- definição editorial de quem pode revisar e publicar conteúdo reputacional.

Credenciais nunca serão solicitadas no chat.
