# ADR 0009 — Observatório territorial e limite reputacional

- Estado: aceita
- Data: 2026-07-31

## Contexto

O escopo inicial acompanha Prefeitura e Câmara de Barreiras. Para explicar a
administração pública local de forma completa, também é necessário mostrar
recursos estaduais e federais, transferências, emendas e atuação de
representantes. Fontes eleitorais, sancionatórias, judiciais e societárias
podem ampliar o controle social, mas criam alto risco de homônimo, culpa por
associação, descontextualização e tratamento excessivo de dados pessoais.

O DataJud exige atenção especial: o schema público documentado não contém
partes, e o termo de uso versão 1.2 limita coleta/tratamento de dados pessoais e
impõe condições para divulgação de material derivado.

## Decisão

Evoluir para um observatório territorial em três camadas:

1. Município em números;
2. recursos destinados a Barreiras;
3. representação e registros oficiais.

Relações serão fatos de primeira classe com evidência, tipo, período, método de
resolução e estado editorial. A visualização usa linguagem neutra e não deriva
culpa, influência ou coordenação.

Sanções serão reconciliadas automaticamente apenas por identificador exato.
Declarações de bens serão sempre vinculadas à eleição. DataJud não será usado
para busca automática por nome e fica bloqueado para associação a pessoas até
revisão jurídica qualificada e esclarecimento formal do CNJ.

React Flow poderá projetar o grafo, mantendo PostgreSQL como fonte de verdade.
Exports reputacionais exigirão autenticação, auditoria e revisão humana.

## Consequências

- maior cobertura territorial sem abandonar o recorte municipal;
- modelo de identidade e proveniência mais rigoroso;
- etapas reputacionais mais lentas e com custo editorial/jurídico;
- impossibilidade de prometer agora busca judicial automática por político;
- nenhuma migration futura é autorizada por este ADR sem contrato e fixture da
  fonte correspondente.

## Alternativas rejeitadas

- tratar qualquer menção a Barreiras como vínculo político confirmado;
- “dossiê”, “suspeito” ou score reputacional como linguagem padrão;
- propagar sanção de empresa a seus sócios ou contratantes;
- adotar Neo4j antes de medir limitações do PostgreSQL;
- usar IA para resolver identidade ou decidir publicação.
