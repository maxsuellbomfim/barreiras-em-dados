# Plano — camada de inferência assistida com cascata de IAs gratuitas

Data: 01/08/2026. Plano aprovado em conceito pelo titular; implementação
condicionada a ADR próprio antes do primeiro uso.

## Papel da IA no projeto (limites inegociáveis)

- a âncora de evidência continua **determinística**: regras versionadas,
  offsets exatos e hashes — reproduzível por qualquer pessoa sem IA;
- a IA atua como **camada de sugestão**: propor campos que as regras não
  capturaram, resumir atos em linguagem simples, classificar tipos de ato;
- **tudo que a IA produzir nasce como inferência `needs_review`**, na mesma
  fila de revisão humana, sempre com o trecho original ao lado;
- IA nunca publica, nunca calcula totais, nunca decide; rótulo público
  distinguirá "fato extraído" de "resumo assistido";
- prompt, modelo e provedor são versionados como qualquer regra
  (`assisted-inference/<versão>`), e a resposta bruta da IA é preservada.

## Cascata de provedores gratuitos (proposta do titular)

| Nível | Provedor | Segredo (GitHub Actions) |
|---|---|---|
| L1 | Groq (Llama 3.x 70B, camada gratuita) | `GROQ_API_KEY` |
| L2 | OpenRouter (modelos com cota gratuita) | `OPENROUTER_API_KEY` |
| L3 | Google Gemini (camada gratuita) | `GEMINI_API_KEY` |
| L4 (avaliar) | NVIDIA NIM (créditos gratuitos de API) | `NVIDIA_API_KEY` |

Regras da cascata:

- esgotou cota/limite do nível N (HTTP 429/402 ou erro de quota), o nível
  N+1 assume a mesma tarefa; o payload registra qual provedor/modelo
  respondeu;
- saída inválida (JSON fora do contrato) não cai para o próximo nível às
  cegas: é registrada como falha do nível e contabilizada;
- cascata esgotada = estado explícito `assisted_inference_unavailable`; o
  fluxo determinístico segue funcionando sem a IA;
- chaves somente em GitHub Secrets; nenhum dado pessoal além do texto do
  diário (que é público) é enviado aos provedores;
- custo alvo: R$ 0. Com doações futuras, um provedor pago entra como L1 e a
  cascata gratuita vira contingência.

## Pré-requisitos antes de implementar

1. peça 3b (OCR) para haver texto das páginas escaneadas;
2. ADR formal (modelos, contratos de saída, amostra de validação, riscos de
   alucinação e viés, política de retenção dos provedores);
3. definição da primeira tarefa assistida (sugerida: campos não capturados
   pelas regras em candidatos já detectados — escopo pequeno e auditável).
