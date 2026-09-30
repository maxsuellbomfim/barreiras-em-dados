# ADR 0091 — Conferência da amostra de qualidade dos atos por IA

## Status

Aceita em 30/09/2026 pelo titular ("não quero ter que decidir nada
humanamente, quero tudo automatizado"; "pode seguir com ... a opção 3").
Supersede, **somente para a métrica de qualidade da extração de atos**, a
exigência do ADR 0011 de amostra conferida por especialista antes de métrica
de precisão.

## Contexto

A amostra `act-quality-sample/1.0.0` (120 páginas, 65 atos) espera conferência
humana na aba "Qualidade dos atos" do admin. Sem ela não há medida de precisão
nem de revocação da extração de nomeações e exonerações. O titular não quer
depender de decisão humana recorrente.

## Decisão

1. Um modelo de visão (cascata gratuita do Gemini, ADR 0011) recebe a
   **imagem da página do PDF oficial** — não o nosso OCR — e a lista de atos
   extraídos dela. Responde, por ato, `correct`/`partial`/`incorrect` e conta
   nomeações e exonerações não extraídas (`act-quality-prompt/1.0.0`).
2. A resposta só é gravada se o código validar o contrato: exatamente os ids
   enviados, vereditos da lista fechada e contagens inteiras de 0 a 200. O PDF
   é conferido pelo SHA-256 antes de rasterizar.
3. A anotação vai para `editorial.act_quality_annotations` (append-only) com
   autor `ai:<modelo>:<versão do prompt>` e o SHA-256 da resposta bruta. Ela
   **não** altera `editorial.editorial_reviews` nem o que está publicado.
4. Os números continuam calculados por código (`act-quality-metrics/1.1.0`),
   agora com filtro de origem: `any`, `human` ou `ai`. Uma anotação humana
   posterior prevalece sobre a da IA na mesma página (a mais recente vale).
5. Qualquer exibição dessas métricas traz o rótulo **"estimativa automática
   por IA, não revisão humana"**, com modelo e versão do prompt.
6. O workflow `annotate-act-quality.yml` roda diariamente e só envia páginas
   sem anotação da versão vigente do prompt; mudar o prompt é nova versão.

## Alternativas

- Esperar revisão humana: bloqueia a medida indefinidamente.
- IA julgando a partir do nosso texto de OCR: mediria o OCR contra ele mesmo.
- IA decidindo publicação de atos: continua vedado; aqui ela só estima
  qualidade, sem efeito sobre o que é publicado.

## Consequências

- A medida existe sem trabalho humano, mas é estimativa: o modelo pode errar
  leitura de páginas ruins. Por isso o rótulo e o filtro de origem.
- Cota gratuita limita o ritmo (~10 chamadas/min); falha de todos os modelos
  não grava nada e a página volta na próxima execução.
- Nenhuma métrica é tornada pública por este ADR; a função segue restrita a
  usuários autenticados do admin.
