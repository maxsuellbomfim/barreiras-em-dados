# 0014 — Dossiês de representação com vínculo territorial explícito

Data: 2026-08-01. Status: aceita (ratificada pelo titular no merge deste PR).

## Contexto

A plataforma passa a manter páginas de pessoas: deputados federais e
estaduais com atuação relacionada a Barreiras, vereadores, secretários
municipais e candidaturas. "Dossiê" aqui significa **registro público
consolidado com fonte por campo** — nunca avaliação, nota, ranking ou
julgamento.

Três riscos concretos justificam regras próprias:

1. **Homônimo**: dois "José da Silva" não são a mesma pessoa. Unificar por
   nome cria calúnia por acidente.
2. **Vínculo territorial inventado**: um deputado é eleito pelo estado
   inteiro. Chamá-lo de "deputado da região" sem critério é opinião.
3. **Ausência de fonte lida como virtude ou defeito**: "nenhuma sanção
   encontrada" não é "ficha limpa"; "sem proposições coletadas" não é
   "não trabalha".

## Decisão

### Identidade
Pessoa só é unificada por **identificador oficial** (id da Câmara, id do
TSE, CPF parcial quando publicado pela fonte). Nome igual **nunca**
unifica. Sem identificador comum, os registros permanecem separados e a
página declara a limitação.

### Vínculo territorial (o critério é público e mensurável)
Um mandatário estadual/federal só aparece como relacionado a Barreiras
por um destes vínculos, sempre exibido com o número que o sustenta:

- **eleitoral**: recebeu votos em Barreiras na eleição (votação nominal
  por município, TSE) — exibe a quantidade e o percentual;
- **orçamentário**: destinou emenda com beneficiário em Barreiras — exibe
  valor e estágio;
- **institucional**: exerce ou exerceu cargo municipal em Barreiras.

Sem nenhum vínculo verificável, a pessoa **não** entra como
"representante da região". Todo vínculo mostra a fonte e a data.

### Conteúdo do dossiê
- Cada campo carrega origem, data de coleta e evidência (`evidence_items`).
- Fato (cargo, mandato, voto registrado), inferência (vínculo derivado),
  e hipótese permanecem visualmente distintos.
- Bens declarados ao TSE são **declaração eleitoral daquele pleito**,
  jamais "patrimônio atual".
- Processos judiciais e sanções: fora deste ADR; entram apenas por
  identificador exato e com parecer jurídico (ADR futuro).
- Ausência de dado é exibida como **"não coletado"** ou **"não
  encontrado nesta fonte"**, nunca como zero, "nada consta" ou elogio.

### Publicação
Perfis seguem o ADR 0012: campos coletados de fonte estruturada oficial
são publicados automaticamente (são espelho fiel do registro); qualquer
texto interpretativo sobre a pessoa exige revisão humana registrada.
Correção pública pelo mesmo canal de issues.

## Consequências

- A cobertura começa parcial e assimétrica (deputados federais têm API
  aberta; vereadores e secretários dependem de fontes locais e do Diário).
  A página declara a cobertura de cada fonte em vez de aparentar completude.
- Nenhuma página de pessoa exibirá agregados comparativos entre pessoas
  nesta fase — comparação exige metodologia revisada por especialista.
