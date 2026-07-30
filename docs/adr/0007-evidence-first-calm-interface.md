# ADR 0007 — Interface calma e centrada em evidências

- Estado: aceita
- Data: 2026-07-30

## Contexto

Uma plataforma de transparência pode criar pressão pública legítima ao reduzir o
custo de verificar documentos. Também pode causar dano ao dramatizar sinais,
misturar fato e inferência ou apresentar pessoas como culpadas sem base.

O portal precisa ser popular e atraente sem transformar indignação em métrica de
produto. O usuário pediu uma direção inspirada no design da Apple.

## Decisão

Adotar uma linguagem visual própria, inspirada em clareza, familiaridade,
resposta, acessibilidade e acabamento. A emoção-alvo é calma, confiança e
controle.

A evidência é a âncora da interface. Documento, trecho, fonte, cobertura e
histórico de correções permanecem próximos do fato apresentado. Materiais
translúcidos são opcionais e restritos a camadas de navegação ou evidência.

Estados reputacionalmente diferentes usam rótulo textual, ícone e tratamento
semântico. O design não emprega placares de corrupção, linguagem acusatória,
movimento dramático ou cor como prova implícita.

As fundações são documentadas agora. A implementação dos componentes começa
somente quando a cadeia de evidência do primeiro fluxo estiver estável.

## Consequências

- o portal terá identidade própria e não copiará marca ou interface da Apple;
- toda tela factual será projetada de dentro para fora a partir da evidência;
- acessibilidade e movimento reduzido entram no componente, não em correção
  posterior;
- gráficos e resumos têm menos prioridade que rastreabilidade;
- o pacote de UI crescerá conforme telas reais, evitando um design system
  especulativo;
- revisões editoriais incluem o efeito reputacional da apresentação visual.

## Alternativas rejeitadas

- construir primeiro uma landing page visual sem dados verificáveis;
- usar dashboards densos como experiência principal;
- adotar estética de denúncia, ranking ou “suspeitômetro”;
- copiar componentes e identidade visual de uma empresa específica.
