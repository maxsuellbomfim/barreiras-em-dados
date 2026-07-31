# ADR 0010 — Perfis políticos compostos e ETLs raw-first

- Estado: aceito
- Data: 31/07/2026

## Contexto

O produto deverá reunir cargos, remuneração, candidaturas, declarações
eleitorais, atividade legislativa, empresas, sanções e referências judiciais de
agentes políticos ligados a Barreiras.

Repositórios de inspiração oferecem scripts que gravam diretamente no Supabase,
apagam períodos inteiros, usam credenciais administrativas, agregam pessoas por
nome e, em alguns casos, inserem dados fictícios. Executá-los como estão
eliminaria a cadeia de custódia e elevaria o risco de homônimo, perda histórica,
exposição pessoal e publicação reputacional indevida.

## Decisão

1. O produto público se chamará **perfil público documentado**, não dossiê.
2. `people` será a identidade central; não haverá tabela monolítica de dossiê.
3. Cada módulo será uma projeção de entidades temporais com evidência própria.
4. Coletores diferentes podem adquirir dados em qualquer ordem; normalização,
   resolução, reconciliação, revisão e publicação têm dependências obrigatórias.
5. Todo ETL grava primeiro no bruto imutável e nunca diretamente na projeção
   pública.
6. Identidade por nome é apenas candidata interna. Publicação exige chave
   apropriada ou decisão humana documentada.
7. Cada fonte recebe role mínima própria. `postgres` e `service_role` não são
   credenciais de ETL.
8. Dados reputacionais nunca são publicados automaticamente.
9. Scores de honestidade, corrupção, letalidade ou risco pessoal ficam
   proibidos.
10. Códigos de referência só podem ser incorporados após revisão de licença,
    segurança, semântica e adaptação ao modelo de evidências.

## Consequências

### Positivas

- correções não apagam versões anteriores;
- cada afirmação pode ser auditada e contestada;
- módulos de alto risco podem permanecer bloqueados sem impedir o perfil básico;
- uma falha de identidade não contamina todos os dados da pessoa;
- o portal pode explicar cobertura e ausência de fonte sem transformar ausência
  de dado em ausência de fato.

### Custos

- o primeiro perfil completo demora mais que uma importação direta;
- são necessários contratos, fixtures e revisões por fonte;
- relações societárias, sanções e processos exigem filas e decisões humanas;
- ETLs de referência serão reescritos em vez de copiados.

## Alternativas rejeitadas

- tabela JSON única por político;
- apagar e recarregar o ano em cada sincronização;
- considerar todos os ETLs independentes até a publicação;
- usar CPF/CNPJ em campos públicos como atalho de reconciliação;
- usar IA para julgar gasto, identidade ou legalidade;
- reproduzir rankings morais de projetos de referência.
