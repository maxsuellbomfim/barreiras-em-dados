# ADR 0038 — Continuidade local quando a IA está sem cota

Data: 04/08/2026. Status: aceito.

## Contexto

As cotas gratuitas dos provedores podem acabar ao mesmo tempo. Isso não deve
impedir a leitura de documentos já preservados nem deixar o cidadão sem uma
explicação factual para atos que o extrator determinístico reconheceu.

## Decisão

- Atos de nomeação e exoneração podem receber um resumo por template local,
  usando somente `person_name`, `position`, número e data já encontrados pelas
  regras e conferidos no trecho oficial.
- O texto de leitura é `clean_excerpt`, uma recomposição determinística do
  trecho preservado. Não é apresentado como saída de IA.
- Ato com pessoa ausente, campos essenciais ausentes ou duas ou mais pessoas
  continua em `needs_review`; o fallback nunca separa pessoas sozinho.
- O Diário Oficial pode receber itens locais apenas para atos de pessoal
  reconhecidos. Contratos, licitações, decretos e avisos sem classificador
  específico permanecem no documento bruto até a cascata voltar.
- Aliases de vereadores recebem somente uma sugestão `pending`, fechada aos
  candidatos oficiais. Caixa, acentos, parênteses e primeiro nome + sobrenome
  são sinais de triagem, não prova de identidade; empate vira `ambiguous`.

Cada fallback registra `provider=local-deterministic`, versão das regras,
hash do trecho e método. A revisão/aceite humano continua sendo a única forma
de criar alias; a publicação automática de atos só ocorre depois da mesma
verificação literal já aplicada aos resultados assistidos.

## Consequências

- A plataforma continua útil mesmo com todas as APIs de IA indisponíveis.
- O painel e o site precisam distinguir claramente “regras determinísticas
  (sem IA)” de “resumo gerado por IA”.
- A cobertura local é deliberadamente menor que a de um modelo: não há
  interpretação livre nem tentativa de preencher lacunas.
