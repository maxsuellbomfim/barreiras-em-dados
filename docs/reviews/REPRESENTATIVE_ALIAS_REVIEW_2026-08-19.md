# Revisão de aliases de vereadores — 19/08/2026

Análise assistida (Claude) da fila `political.representative_alias_suggestions`
com 40 sugestões pendentes, fundamentada exclusivamente em evidência do
próprio acervo: elenco atual da CM Barreiras (19 titulares,
`cm_barreiras_vereador`), votação TSE de Barreiras (2022 e 2024,
`tse_votacao_barreiras`) e aliases já aceitos. **Nada foi aceito ou publicado
por este relatório**: as decisões abaixo são recomendações para o revisor
ativo aplicar na fila do `apps/admin`, que continua sendo o único caminho de
aceitação (RPC `api.review_representative_alias_suggestion`).

## Auditoria dos 53 aliases ativos

Todos os 53 aliases ativos em `political.representative_aliases` foram
conferidos um a um contra o elenco: **nenhum vínculo errado** — todas as
linhas mapeiam variantes de caixa/acento/espaçamento/rótulo editorial
("VEREADOR(A) …") para a pessoa correta.

## Recomendação: ACEITAR (26 sugestões)

Variantes do nome de titulares em exercício. Agrupadas por pessoa
(`representative_external_id` abreviado):

| Pessoa (elenco CM) | Sugestões pendentes (`observed_name`) | Evidência |
|---|---|---|
| Allan Kardec Bonfim Bacelar (…f7b7c3fd16a711f7) | "Allan Kardec Bomfim Bacelar" | Grafia Bomfim/Bonfim; único Allan Kardec no elenco |
| Antônio Rocha Teixeira (Tatico) (…5cc47cedc474435f) | "Antonio Rocha Teixeira"; "Antônio Rocha Teixeira"; "VEREADOR ANTÔNIO ROCHA TEIXEIRA" | Igualdade literal após remoção de acento/rótulo "VEREADOR" |
| Ben-Hir Aires de Santana (…8a7e2a48a68faf3e) | "Ben Hir Aires de Santana"; "BEN-HIR  AIRES DE SANTANA"; "BEN-HIR AIRES DE SANTANA" (com quebra de linha); "Ben-Hir Aires Santana" | Hífen/espaços/caixa; "sem de" é o mesmo nome; único Ben-Hir |
| Carmélia de Carvalho de Souza (…8ff5a9694d3167db) | "Carmélia Carvalho De Sousa" | Sousa/Souza + partícula; única Carmélia |
| Dicíola Figueirêdo de Andrade Baqueiro (…6de82b323fafc3bf) | "DICÍOLA FIGUEIRÊDO DE ANDRADE BAQUEIRO"; "Diciola Figueredo de Andrade Baqueiro" | Caixa; Figueredo/Figueirêdo; única Dicíola |
| Heleina Braz da Silva Chaves (Teteia Chaves) (…7498d5a73db47cbf) | "Heleina Braz da Silva"; "VEREADORA HELEINA BRAZ DA SILVA CHAVES (TETEIA" | Forma curta já aceita antes; segunda é truncamento da fonte |
| Hipólito dos Passos de Deus (…ca5dffb0034b8dac) | "VEREADOR HIPÓLITO DOS PASSOS DE DEUS" | Rótulo + igualdade literal |
| Izabel Rosa de Oliveira Santos (Beza) (…b61169a98a68df6a) | "ISABEL ROSA DE OLIVEIRA DOS SANTOS"; "IZABEL ROSA OLIVEIRA DOS SANTOS" | Isabel/Izabel; partículas; única Izabel |
| João Felipe de Melo Lacerda (…944b81b35506230f) | "JOÃO FELIPE  DE MELO LACERDA"; "JOÃO FELIPE DE MELO  LACERDA"; "JOAO FELIPE DE MELO LACERDA"; "JOÃO FELIPE DE MELO LACERDA" (com quebra de linha) | Caixa/acento/espaços duplos |
| Maria das Graças Melo do Espírito Santo (Drª. Graça) (…aa1a622e47a11a1d) | "Maria Das Graças Melo do Espirito Santo"; "Maria das Graças Melo do Espírito Santo"; "MARIA DAS GRAÇAS MELO DO ESPÍRITO SANTO" (com quebra de linha) | Caixa/acento |
| Valdimiro José dos Santos Filho (…f852d49c295630dd) | "VEREADOR VALDIMIRO JOSÉ DOS SANTOS" | Sem "Filho"; único Valdimiro; TSE 2024 "ELEITO POR QP" |
| Yure Ramon da Silva Cunha (…9a3cb3b43364dfdf) | "VEREADOR YURE RAMON DA SILVA CUNHA"; "Yure Ramon da Silva Cunha" | A segunda é igualdade exata com o canônico (a IA marcou "ambiguous" por inconsistência) |

## Recomendação: NÃO VINCULAR — suplentes de 2024 em exercício (5 sugestões)

São autoras/autores reais de itens legislativos recentes, mas **não estão no
elenco de 19 titulares** — o TSE 2024 os registra como suplentes de
vereador. Vincular ao titular errado seria falso; deixar como
`needs_more_evidence` com a nota abaixo até existir perfil próprio:

| `observed_name` | Evidência TSE 2024 |
|---|---|
| "ALCIONE RODRIGUES DE MACEDO" | Vereadora, situação SUPLENTE (urna "Alcione Rodrigues") |
| "Ivete Maria Carneiro De Sousa Ricardi" | Vereadora, SUPLENTE (urna "Pastora Ivete Ricardi") |
| "Sileno Cerqueira Bispo dos Santos"; "Sileno Cerqueira Bispo Dos Santos"; "Sileno de Cerqueira Bispo dos Santos" | Vereador, SUPLENTE (urna "Dr Sileno") |

Nota sugerida: "Suplente de 2024 em exercício; sem perfil no elenco atual da
CM. Aguardando decisão de modelagem para suplentes."

## Recomendação: NÃO VINCULAR — sem identidade no acervo (8 sugestões)

Autores de itens de legislaturas anteriores; sem correspondência no elenco
atual nem no TSE 2022/2024 (o acervo TSE não cobre eleições anteriores), e o
registro histórico (`political.historical_representatives`) está vazio:

- "Antônio Carlos De Almeida Matos"
- "Dr José Barbosa Pires Jr"; "DR. JOSÉ BARBOSA PIRES JÚNIOR"; "José Barbosa Pires Jr"
- "EUGÊNIO DE ARAÚJO FERNANDES"
- "Marileide Carvalho de Souza Pinto"
- "Núbia Ferreira Souza de Araújo"
- "Marcos Reis Macedo Ramos" — única ocorrência TSE é Deputado Estadual
  2022 (SUPLENTE), não vereador; não vincular ao elenco municipal.

Nota sugerida: "Autor(a) de legislatura anterior; fora do elenco atual.
Aguardando povoamento do registro histórico."

## Caso especial (1 sugestão) — RESOLVIDO

- "VEREADORA MARIA DAS GRAÇAS MELO DE OLIVEIRA" — o sobrenome diverge do
  canônico ("de Oliveira" × "do Espírito Santo"). A única "Maria das Graças
  Melo" no TSE 2022/2024 é a Drª Graça (eleita 2024). **Confirmado pelo
  titular em 19/08/2026: é a mesma pessoa (Drª. Graça)** — o sobrenome é
  grafia da fonte. Decisão: aceitar como `other`, com a confirmação
  registrada na nota da revisão.

## Oito sugestões novas de 19/08 (revisadas no mesmo lote)

A execução semanal do sugestor criou mais 8 pendências depois da primeira
análise; todas revisadas com o mesmo critério:

**ACEITAR (5):** "BEN-HIR AIRES DE SANTANA" com quebras de linha CRLF;
"HIPÓLITO DOS PASSOS DE DEUS" com CRLF; "Hipólito Dos Passos de Deus"
(igualdade literal — a cascata reteve por validação, não por dúvida);
"Hipólito Dos Passos De Deusa" (typo "Deusa" da própria fonte, mesma classe
de Figueredo/Bomfim); "Izabel Rosa Oliveira Dos Santos" (sem o "de").

**NÃO VINCULAR (3):** "ANTONIO CARLOS DE ALMEIDA MATOS" e "Eugênio De
Araújo Fernandez" (Fernandez/Fernandes — legislatura anterior, sem
identidade no acervo); e **"OTONIEL NASCIMENTO TEIXEIRA" — é o Prefeito
eleito em 2024 (TSE, urna OTONIEL)**: autoria do Executivo em leis. O
conjunto fechado desta fila só contém vereadores, então o vínculo correto
exige modelagem de autoria do Executivo (lacuna estrutural nº 4: leis de
iniciativa do Prefeito continuarão re-sugerindo esse nome até existir esse
perfil).

## Aplicação da revisão

As 48 decisões (32 aceitar, 16 `needs_more_evidence`) estão prontas
em `supabase/migrations/20260819063000_apply_alias_review_2026_08_19.sql`.
O arquivo é executado **pelo próprio revisor ativo** no SQL Editor — a
execução é o ato de revisão registrada (reviewed_by/approved_by com a
identidade dele) — e só toca sugestões ainda pendentes: o que já tiver
sido decidido na fila do admin permanece intocado. A alternativa continua
sendo revisar item a item no `apps/admin` com esta tabela ao lado.

## Lacunas estruturais observadas (para fatias futuras)

1. **Suplentes em exercício** assinam leis e indicações, mas o elenco público
   só tem os 19 titulares — os itens deles ficam sem perfil vinculável (hoje
   exibidos com o nome da fonte, o que é correto porém sem link).
2. **Registro histórico vazio**: 8 nomes pendentes não têm para onde apontar;
   povoar `political.historical_representatives` destravaria a fila.
3. As sugestões da cascata marcam "ambiguous" com confiança 0 até para
   igualdade exata (ex.: "Yure Ramon da Silva Cunha") — um pré-classificador
   determinístico de igualdade literal reduziria ruído da fila sem tocar na
   regra de que só revisor ativo aceita.
