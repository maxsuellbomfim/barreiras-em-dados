# ADR 0075 — Seleção privada de documentos da folha

- Estado: aceita
- Data: 2026-08-22

## Contexto

O publicador da folha opera hoje com a role técnica compartilhada pelos
coletores. Essa role já possui leitura bruta necessária à preservação e ao
reprocessamento; as aplicações públicas não possuem esse acesso. A seleção
direta combinava artefato, registro, fonte, endpoint,
agregado e falha de extração. Em produção, essa consulta retornou zero para a
role do worker mesmo quando a mesma evidência, consultada administrativamente,
confirmava um PDF regular pendente de março de 2024. Nenhum erro SQL era
emitido, criando o risco de uma lacuna silenciosa.

## Decisão

A seleção de PDFs pendentes e a contagem de documentos não resolvidos passam
por funções privadas `SECURITY DEFINER` no schema `hr`. As funções:

- fixam a fonte, o endpoint, os tipos de registro, os títulos oficiais e as
  versões do parser e do job dentro do código versionado da migration;
- validam competência, intervalo fiscal e limite máximo de vinte documentos;
- preservam as exclusões de estagiários, terceirizados, artefatos sem linhagem
  exata, versões já processadas e falhas terminais da versão atual;
- têm `search_path` vazio e concedem execução apenas a `collector_worker`;
- não ampliam os privilégios preexistentes da role técnica e não concedem
  execução a `anon` ou `authenticated`.

Por esse caminho, o publicador recebe somente os metadados mínimos necessários
para verificar o hash, ler o PDF privado e persistir o agregado. O site continua
consumindo apenas a projeção pública agregada. Criar uma role de login exclusiva
para o publicador, sem os privilégios brutos compartilhados pelos coletores,
fica registrado como endurecimento posterior e exigirá rotação coordenada das
credenciais do workflow.

## Consequências

- a RLS permanece fechada para as aplicações públicas e deixa de transformar
  documento existente em fila aparentemente vazia no publicador;
- alterações no contrato de fonte ou nas versões exigem nova migration
  auditável;
- entradas inválidas falham explicitamente, em vez de ampliar a consulta;
- testes de banco conferem seleção, exclusões e privilégios das funções.
- o comprometimento da role compartilhada ainda alcançaria o acervo bruto;
  reduzir esse raio de acesso depende da role exclusiva registrada acima.
