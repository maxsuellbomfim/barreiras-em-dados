# Instruções para agentes — Barreiras 360

## Antes de editar

1. Leia `docs/CURRENT_STATUS.md` e apenas o documento do domínio em que vai
   atuar. `docs/ROADMAP.md` é histórico detalhado, não leitura inicial.
2. Localize o menor fluxo vertical que entrega valor público verificável.
3. Use `rg` para encontrar código e testes relacionados; não leia todas as
   migrations nem todo o repositório.
4. Preserve mudanças não relacionadas e trabalhe em branch/worktree própria.

## Como implementar

- Um PR deve resolver um resultado observável, com escopo pequeno e reversível.
- Escreva primeiro um teste que falhar pelo motivo esperado; depois faça a
  menor implementação capaz de torná-lo verde.
- Reutilize contratos, componentes e clientes existentes antes de criar outra
  abstração ou dependência.
- Não adicione biblioteca, plugin ou serviço sem demonstrar a lacuna que ele
  resolve e o custo operacional que introduz.
- Listas públicas recebem metadados e paginação; conteúdo grande é carregado
  apenas na página de detalhe. Nunca hidrate o navegador com arquivos integrais
  apenas porque um `<details>` começa fechado.
- Mantenha HTML semântico, foco visível, navegação por teclado, largura móvel
  sem overflow da página e texto compreensível sem jargão técnico.

## Integridade editorial e de dados

- Fonte indisponível, dado ausente, zero oficial e período não coletado são
  estados diferentes.
- Não some eleições, turnos ou estágios financeiros incompatíveis.
- Não atribua autoria, identidade, execução ou irregularidade por similaridade
  textual. Preserve a evidência e bloqueie a conclusão ambígua.
- LLM pode auxiliar leitura e classificação, mas não calcula totais, não muda
  o texto oficial e não decide publicação reputacional.
- Todo fato público deve apontar para fonte oficial e evidência preservada.
- Não reescreva migrations aplicadas. Correções usam nova versão auditável.

## Verificação e handoff

- Execute o teste específico durante o ciclo e, antes do handoff, `pnpm test`,
  typecheck/build das aplicações afetadas e verificações Python proporcionais.
- Valide a experiência no celular e no desktop quando houver mudança visual.
- Informe o que foi comprovado, o que segue limitado pela fonte e o próximo
  menor passo. Workflow verde não prova cobertura nem qualidade dos dados.
