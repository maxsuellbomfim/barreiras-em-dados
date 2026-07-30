# Portões de conformidade

## Situação

**Prosseguir com condições.** O propósito de controle social é legítimo, mas a
junção sistemática de fontes sobre pessoas, remuneração e relações pode elevar
o risco à privacidade, honra e imagem. Este documento é uma triagem de produto,
não um parecer jurídico.

## Antes de publicar dados sobre pessoas

1. inventariar cada dado pessoal, fonte, finalidade, hipótese legal, acesso,
   compartilhamento e retenção;
2. aplicar teste documentado de necessidade e proporcionalidade;
3. elaborar RIPD antes de tratamentos potencialmente de alto risco, sobretudo
   cruzamento de fontes, perfil público longitudinal e folha individual;
4. definir controlador, operadores, encarregado/canal de privacidade e
   contratos com fornecedores;
5. oferecer aviso de privacidade, acesso, correção, contestação e registro de
   decisões;
6. obter revisão jurídica brasileira de privacidade, imprensa e direito
   eleitoral antes do lançamento público.

A ANPD recomenda RIPD quando o tratamento puder gerar alto risco e orienta
produzi-lo antes do início, com dados tratados, metodologia, finalidade,
hipótese legal, riscos e salvaguardas:
<https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd>.

Referências legais primárias:

- LGPD: <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm>;
- LAI: <https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm>.

## Riscos e controles mínimos

| Risco | Nível | Controle |
|---|---|---|
| rotular pessoa como corrupta por automação | crítico | proibido; revisão humana e jurídica |
| publicar CPF, descontos ou dado sensível | alto | bloqueio por schema, minimização e revisão |
| associar homônimos ou extrair ato errado | alto | evidência, confiança, dupla revisão e correção |
| combinar fontes para inferir vínculos | alto | RIPD, fonte primária e estado “não verificado” |
| receber denúncias/acusações abertas | alto | não lançar no MVP; futura moderação e assessoria |
| publicar em período eleitoral com viés | alto | política eleitoral, isonomia e log editorial |
| perder documento removido da origem | médio | cópia imutável, hash e data da coleta |
| enviar alertas sem consentimento | médio | opt-in, minimização e descadastro |

## Política para 2026

Como o projeto nasce em ano de eleição geral, conteúdo factual local ainda
precisa de política editorial que separe jornalismo/dados de propaganda,
documente critérios uniformes e vede impulsionamento político seletivo. As
regras de propaganda na internet foram atualizadas pelo TSE para 2026:
<https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-755-de-2-de-marco-de-2026>.

Qualquer campanha paga, parceria partidária, pedido de voto, enquete eleitoral
ou conteúdo sintético sobre candidatura exige análise jurídica específica.

## Aprovações necessárias

- responsável editorial: metodologia, linguagem e isonomia;
- responsável de qualidade: identidade, completude e reprodução;
- responsável de segurança/privacidade: acesso, retenção e incidente;
- advogado qualificado no Brasil: política de publicação, LGPD, honra/imagem,
  direitos autorais das fontes e regras eleitorais;
- revisão extraordinária para qualquer conclusão com impacto reputacional.

## Evidências a manter

- inventário de tratamento e RIPD versionados;
- termos/licenças de cada fonte e data da verificação;
- checklist e decisão de cada revisão;
- versões publicadas, correções e retiradas;
- logs de acesso administrativo e incidentes;
- consentimentos e descadastros de alertas.
