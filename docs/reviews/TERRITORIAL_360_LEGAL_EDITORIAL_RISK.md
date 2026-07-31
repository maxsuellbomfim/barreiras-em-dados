# Avaliação preliminar de risco jurídico-editorial — visão territorial 360

**Data:** 31/07/2026

**Avaliador:** revisão técnica preliminar assistida; não constitui parecer jurídico

**Matéria:** expansão para dados eleitorais, judiciais, sancionatórios,
societários, grafos e exportações

**Privilegiado:** não

Esta avaliação organiza riscos para decisão de produto. Deve ser revisada por
profissional jurídico qualificado no Brasil, especialmente em LGPD, liberdade
de expressão/imprensa e responsabilidade civil.

## 1. Descrição

A reunião de bases públicas pode tornar fatos acessíveis, mas também amplificar
dano por homônimo, desatualização, papel processual mal interpretado, culpa por
associação e persistência de dados pessoais. O risco nasce do cruzamento e da
apresentação, não apenas da publicidade isolada de cada fonte.

## 2. Matriz

Escala: severidade e probabilidade de 1 a 5; pontuação é o produto.

| ID | Risco | S | P | Pontos | Nível | Decisão inicial |
|---|---|---:|---:|---:|---|---|
| R-360-01 | DataJud associado automaticamente a político por nome | 5 | 4 | 20 | crítico | bloquear |
| R-360-02 | sanção de empresa atribuída a homônimo ou propagada a sócio/agente | 4 | 4 | 16 | crítico | ID exato + revisão |
| R-360-03 | grafo visual induzir culpa por associação | 4 | 4 | 16 | crítico | evidência por aresta + linguagem neutra |
| R-360-04 | IA produzir conclusão jurídica/reputacional | 5 | 4 | 20 | crítico | proibir publicação/decisão |
| R-360-05 | bens eleitorais apresentados como patrimônio atual ou enriquecimento | 4 | 3 | 12 | alto | vincular a eleição + metodologia |
| R-360-06 | exportação amplificar perfil reputacional ou dado excessivo | 4 | 3 | 12 | alto | autenticar, revisar e auditar |
| R-360-07 | “secretaria útil” criar julgamento subjetivo/selectivo | 3 | 3 | 9 | médio | métricas factuais e simétricas |
| R-360-08 | somar valores anunciados, empenhados e pagos | 3 | 3 | 9 | médio | estágios separados e testes |
| R-360-09 | relação territorial de deputado definida subjetivamente | 3 | 3 | 9 | médio | taxonomia pública + evidência |

## 3. Fatores agravantes

- nomes comuns e identificadores mascarados;
- atualizações e retificações sem aviso;
- resultados de busca sem papel processual;
- grafos que visualmente sugerem causalidade;
- exportação que remove contexto da interface;
- modelos de IA com linguagem confiante;
- retenção indefinida de perfis pessoais agregados.

## 4. Fatores mitigadores existentes

- camada bruta append-only e evidência por afirmação;
- publicação apenas após estado `approved`;
- separação entre fato, inferência, anomalia e hipótese;
- proibição de score reputacional;
- minimização e histórico de correções;
- cálculos financeiros determinísticos.

## 5. Opções

| Opção | Efetividade | Esforço | Recomendada |
|---|---|---|---|
| lançar todos os cruzamentos como “beta” | baixa | baixo | não |
| integrar primeiro fluxos financeiros e atividade legislativa | alta | médio | sim |
| sanções apenas por identificador exato | alta | médio | sim |
| parecer jurídico + contato formal com CNJ antes de DataJud pessoal | alta | médio | sim |
| revisão dupla para perfis, grafos e exports reputacionais | alta | alto | sim |
| excluir definitivamente qualquer dado reputacional | alta para risco, baixa para missão | baixo | não neste momento |

## 6. Abordagem recomendada

1. priorizar receitas, transferências, emendas e atividade legislativa;
2. instituir taxonomia pública de vínculo territorial;
3. integrar CEIS/CNEP somente por CNPJ/identificador exato;
4. tratar QSA como vínculo cadastral, nunca como indício;
5. mostrar bens como declaração vinculada ao pleito;
6. bloquear associação pessoal via DataJud;
7. exigir revisão dupla antes de qualquer grafo ou export reputacional;
8. realizar avaliação jurídica antes de iniciar coleta em escala.

## 7. Risco residual

Com os controles, fluxos financeiros e legislativos ficam em risco
médio/baixo, sujeito à qualidade da fonte. Perfis sancionatórios, societários e
eleitorais permanecem em risco médio. DataJud pessoal permanece crítico e
bloqueado até mudança das condições.

## 8. Monitoramento

- revisar termos e schemas antes de cada execução de backfill;
- reavaliar semestralmente ou quando a fonte mudar;
- medir correções, conflitos de identidade e falsos positivos;
- suspender projeção diante de contestação material;
- manter canal de correção e direito de resposta.

## 9. Próximos passos

1. responsável editorial: aprovar nomenclatura neutra antes do design;
2. equipe de dados: criar contratos apenas após descoberta de cada fonte;
3. advogado externo: revisar DataJud, QSA, exports e base/finalidade LGPD antes
   da etapa 7;
4. responsável pelo projeto: solicitar token CGU somente quando a etapa 7
   entrar no ciclo;
5. segurança: modelar ameaça de grafo e exportação antes de implementação.
