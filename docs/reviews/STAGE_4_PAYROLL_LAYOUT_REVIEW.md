# Revisão da Etapa 4 — leiaute agregado da relação de servidores

- Data da observação: 21/08/2026
- Fonte: Portal da Transparência da Prefeitura de Barreiras
- Recurso: `servidores`
- Registro do catálogo: `id_serv=244`, `tipo=1`, competência 07/2026
- Documento oficial:
  `https://barreiras.mtransparente.com.br/admin//data/SERVIDORES060826145033.pdf`
- SHA-256:
  `411cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8`
- Páginas: 495

## Leiaute comprovado

O PDF possui texto embutido e declara, em cada lotação, uma linha `Total de
Funcionários` com quantidade, provento, desconto e líquido. Ao final, declara
uma única linha `Total de Funcionários Geral` com os mesmos quatro campos.

Na competência observada, foram reconhecidos 133 subtotais. A soma exata desses
subtotais coincide com o total geral:

| Medida declarada | Valor |
| --- | ---: |
| Vínculos | 8.184 |
| Proventos | R$ 34.971.971,48 |
| Descontos | R$ 10.422.982,78 |
| Líquido | R$ 24.548.988,70 |

Em cada subtotal e no total geral, `provento - desconto = líquido`. A soma dos
133 subtotais também fecha nas quatro medidas. Nenhum valor foi calculado por
IA ou ponto flutuante.

## Contrato implementado

`payroll-report-aggregate/1.0.0`:

1. exige, na mesma linha de cabeçalho, matrícula, nome, cargo, regime/vínculo,
   provento, desconto e líquido;
2. tolera somente a variação de acentuação/mojibake já observada na extração;
3. exige pelo menos um subtotal e exatamente um total geral;
4. valida a aritmética de cada total;
5. exige que a soma dos subtotais coincida integralmente com o total geral;
6. devolve somente quantidade e totais monetários agregados.

Nomes, matrículas, cargos, lotações, datas individuais e componentes de
desconto não fazem parte do objeto retornado pelo parser.

## Limites e próxima etapa

- o contrato cobre apenas `tipo=1` no leiaute comprovado;
- estagiários (`tipo=3`) contêm CPF e dados bancários e ficam fora da projeção;
- terceirizados (`tipo=4`) têm leiaute escaneado e significado contratual
  distinto; não serão somados à folha de servidores;
- nenhum agregado está público ainda. A próxima etapa é persistir a competência
  validada com linhagem até o PDF e criar uma RPC que nunca retorne linhas
  individuais.
