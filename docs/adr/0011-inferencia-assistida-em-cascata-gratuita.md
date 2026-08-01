# ADR 0011 — Inferência assistida por IA em cascata de provedores gratuitos

Data: 01/08/2026. Status: proposto (aprovado em conceito pelo titular;
vigora com o merge deste documento).

## Contexto

A extração determinística cobre os padrões previstos, mas diários reais têm
variações que regras fixas não capturam, e a missão do projeto inclui
"linguagem que todo mundo entende". O titular decidiu usar provedores de IA
com camada gratuita, em cascata, para custo zero até haver doações.

## Decisão

1. **A IA é camada de sugestão, nunca de decisão ou publicação.** A âncora
   de evidência permanece determinística (ADR 0005): regras versionadas,
   offsets e hashes. Nada produzido por IA é publicado sem revisão humana
   registrada.
2. **Toda saída de IA nasce como inferência `needs_review`**, exibida na
   fila ao lado do trecho original e claramente rotulada como assistida,
   inclusive no site público quando aprovada ("resumo assistido, revisado
   por pessoa").
3. **Cascata de provedores**: L1 Groq → L2 OpenRouter → L3 Google Gemini →
   L4 NVIDIA NIM (avaliação). Esgotamento de cota (HTTP 429/402) promove o
   nível seguinte; resposta fora do contrato JSON é falha do nível,
   registrada, sem repasse cego; cascata esgotada vira estado explícito
   `assisted_inference_unavailable` e o fluxo determinístico segue.
4. **Rastreabilidade total**: cada resultado registra provedor, modelo,
   versão do prompt (`assisted-inference/<versão>`), resposta bruta
   preservada e hash do texto de entrada. Prompts são versionados no
   repositório como qualquer regra.
5. **Privacidade**: só o texto público do diário é enviado aos provedores;
   nunca dados do revisor, credenciais ou conteúdo interno. Chaves vivem
   somente em GitHub Secrets (`GROQ_API_KEY`, `OPENROUTER_API_KEY`,
   `GEMINI_API_KEY`, futura `NVIDIA_API_KEY`).
6. **Primeira tarefa autorizada** (escopo pequeno e auditável): sugerir
   valores para campos `not_found` de candidatos já detectados e propor um
   resumo em linguagem simples por candidato. Extração de novos candidatos
   por IA, totais e classificações reputacionais permanecem proibidos
   (ADR 0005 e regras inegociáveis).
7. **Custo**: alvo R$ 0. Com doações, um provedor pago assume o L1 e a
   cascata gratuita vira contingência; este ADR não muda.

## Consequências

- ganho de cobertura e legibilidade sem ceder a cadeia de custódia;
- dependência de cotas gratuitas voláteis — mitigada pela cascata e pelo
  estado explícito de indisponibilidade;
- exige monitorar deriva de modelos: a versão do modelo respondente fica
  registrada por resultado, permitindo auditoria retroativa;
- amostra de validação com especialista (gate da 1B) continua exigida antes
  de qualquer métrica pública de precisão.
