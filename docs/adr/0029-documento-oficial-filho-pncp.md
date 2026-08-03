# ADR 0029 — Documento oficial filho do PNCP

## Status

Proposto para revisão no PR desta etapa.

## Contexto

Os artefatos brutos ficam em um bucket privado, com acesso restrito às
identidades técnicas autorizadas. Tornar o bucket público para facilitar a
consulta destruiria a separação entre preservação interna e publicação.

## Decisão

Quando um registro PNCP possuir um artefato filho do tipo `document`, a API
pública exibirá somente os metadados e a URL HTTPS oficial do documento:

- URL original publicada pelo órgão ou PNCP;
- hash SHA-256 do documento preservado;
- data de coleta;
- indicação de que o documento foi preservado.

O objeto interno do Storage não será exposto. A fonte oficial continua sendo a
referência primária e o documento preservado é uma cópia de auditoria.

## Consequências

- O cidadão pode abrir o documento oficial quando a fonte o disponibiliza.
- A plataforma mantém a cópia imutável sem abrir o bucket bruto.
- Registros sem documento filho continuam visíveis com estado explícito.
- O contrato do resumo passa a `pncp-execution-links/1.2.0`.

## Próximo passo

Se a publicação de cópias no portal se tornar necessária, criar uma rota de
acesso assinado com autorização e expiração, nunca uma política pública ampla
no bucket de artefatos.
