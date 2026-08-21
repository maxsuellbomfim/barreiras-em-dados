import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  groupCguLegislatureRankings,
  parseCguFederalAmendmentRankingRows,
  parseCguFederalAmendmentRows,
  parseCguLegislatureRankingRows,
} from "../../apps/web/lib/cgu-federal-amendments.mjs";
import {
  cguExecutionAuthorHref,
  cguExecutionResultCountCopy,
  filterCguExecutionAmendments,
  resolveCguExecutionFilters,
} from "../../apps/web/lib/cgu-execution-filter.mjs";

const SHA = "c".repeat(64);
const resourcesPage = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

function executionRow(overrides = {}) {
  return {
    fiscal_year: 2023,
    amendment_code: "202340720005",
    has_official_code: true,
    amendment_number: "0005",
    amendment_type: "Emenda Individual - Transferências com Finalidade Definida",
    author_kind: "person",
    author_code: "4072",
    author_key: "tito",
    author_name: "TITO",
    author_identified: true,
    locality: "BARREIRAS - BA",
    function_code: "05",
    function_name: "Defesa nacional",
    subfunction_code: "153",
    subfunction_name: "Defesa terrestre",
    program_code: "6012",
    program_name: "DEFESA NACIONAL",
    action_code: "219D",
    action_name: "ADEQUACAO DE ATIVOS",
    budget_plan_code: "0000",
    budget_plan_name: "DESPESAS DIVERSAS",
    committed_amount: "199925.68",
    liquidated_amount: "199925.68",
    paid_amount: "199925.68",
    outstanding_registered_amount: "0.00",
    outstanding_cancelled_amount: "0.00",
    outstanding_paid_amount: "0.00",
    effective_paid_amount: "199925.68",
    transferegov_link_status: "not_found_in_transferegov",
    transferegov_reconciliation_key: null,
    source_row_number: 75382,
    source_url:
      "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip",
    artifact_sha256: SHA,
    collected_at: "2026-08-16T12:00:00+00:00",
    methodology_version: "cgu-federal-amendment-executions/1.0.0",
    ...overrides,
  };
}

function rankingRow(overrides = {}) {
  return {
    rank_position: 1,
    author_kind: "person",
    author_key: "tito",
    author_name: "TITO",
    author_code: "4072",
    amendment_count: 2,
    committed_amount: "699925.68",
    effective_paid_amount: "699925.68",
    first_year: 2022,
    last_year: 2023,
    ranking_amount_stage: "committed",
    methodology_version: "cgu-federal-amendment-ranking/1.0.0",
    ...overrides,
  };
}

test("valores numéricos do PostgREST são aceitos sem perder centavos", () => {
  const parsed = parseCguFederalAmendmentRows([
    executionRow({
      committed_amount: 500000.0,
      liquidated_amount: 500000.0,
      paid_amount: 88306.04,
      outstanding_registered_amount: 411693.96,
      outstanding_cancelled_amount: 0.0,
      outstanding_paid_amount: 411693.96,
      effective_paid_amount: 500000.0,
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].paidAmount, "88306.04");
  assert.equal(parsed[0].effectivePaidAmount, "500000");
  const ranking = parseCguFederalAmendmentRankingRows(
    [
      rankingRow({
        committed_amount: 1956725.4,
        effective_paid_amount: 1845798.28,
      }),
    ],
    "person",
  );
  assert.notEqual(ranking, null);
  assert.equal(ranking[0].committedAmount, "1956725.4");
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({
        committed_amount: Number.POSITIVE_INFINITY,
      }),
    ]),
    null,
    "números não finitos continuam rejeitados",
  );
});

test("linha oficial da CGU preserva estágios separados e evidência", () => {
  const parsed = parseCguFederalAmendmentRows([executionRow()]);
  assert.notEqual(parsed, null);
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].amendmentCode, "202340720005");
  assert.equal(parsed[0].effectivePaidAmount, "199925.68");
  assert.equal(parsed[0].transferegovLinkStatus, "not_found_in_transferegov");
  assert.equal(parsed[0].artifactSha256, SHA);
});

test("pago efetivo diferente de pago + restos pagos é rejeitado", () => {
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ effective_paid_amount: "199925.69" }),
    ]),
    null,
  );
});

test("linha sem código oficial fica visível, mas nunca com vínculo", () => {
  const parsed = parseCguFederalAmendmentRows([
    executionRow({
      amendment_code: "Sem informação",
      has_official_code: false,
      amendment_number: "S/I",
      author_code: "S/I",
      author_name: "Sem informação",
      author_key: "sem informação",
      author_identified: false,
      transferegov_link_status: "code_unavailable",
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].authorIdentified, false);
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({
        amendment_code: "Sem informação",
        has_official_code: true,
      }),
    ]),
    null,
    "has_official_code deve refletir o formato real do código",
  );
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ transferegov_link_status: "code_unavailable" }),
    ]),
    null,
    "código oficial presente não pode ser rotulado como indisponível",
  );
});

test("vínculo confirmado exige chave de reconciliação; demais estados a proíbem", () => {
  const matched = parseCguFederalAmendmentRows([
    executionRow({
      transferegov_link_status: "matched_transferegov_unique",
      transferegov_reconciliation_key: "official:9001:11110001",
    }),
  ]);
  assert.notEqual(matched, null);
  assert.equal(
    matched[0].transferegovReconciliationKey,
    "official:9001:11110001",
  );
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ transferegov_link_status: "matched_transferegov_unique" }),
    ]),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({
        transferegov_reconciliation_key: "official:9001:11110001",
      }),
    ]),
    null,
  );
});

test("evidência insegura ou versão de metodologia divergente invalida o lote", () => {
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ source_url: "http://espelho-nao-oficial.example/z.zip" }),
    ]),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ artifact_sha256: "zz" }),
    ]),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentRows([
      executionRow({ methodology_version: "cgu-federal-amendment-executions/9.9.9" }),
    ]),
    null,
  );
});

test("ranking individual aceita somente pessoas em posições sequenciais", () => {
  const parsed = parseCguFederalAmendmentRankingRows(
    [
      rankingRow(),
      rankingRow({
        rank_position: 2,
        author_key: "afonso florence",
        author_name: "AFONSO FLORENCE",
        author_code: "1111",
        amendment_count: 1,
        committed_amount: "400000.00",
        effective_paid_amount: "400000.00",
        first_year: 2021,
        last_year: 2021,
      }),
    ],
    "person",
  );
  assert.notEqual(parsed, null);
  assert.deepEqual(
    parsed.map((row) => [row.rankPosition, row.authorName]),
    [[1, "TITO"], [2, "AFONSO FLORENCE"]],
  );
  assert.equal(
    parseCguFederalAmendmentRankingRows(
      [rankingRow(), rankingRow({ rank_position: 3 })],
      "person",
    ),
    null,
    "posições fora de sequência indicam resposta corrompida",
  );
  assert.equal(
    parseCguFederalAmendmentRankingRows(
      [rankingRow({ author_kind: "bench", author_name: "BANCADA DA BAHIA" })],
      "person",
    ),
    null,
    "bancada não pode aparecer no ranking individual",
  );
});

test("ranking coletivo aceita bancadas e comissões, nunca pessoas", () => {
  const parsed = parseCguFederalAmendmentRankingRows(
    [
      rankingRow({
        author_kind: "bench",
        author_key: "bancada da bahia",
        author_name: "BANCADA DA BAHIA",
        author_code: "7106",
        amendment_count: 1,
        committed_amount: "3013986.00",
        effective_paid_amount: "3013986.00",
        first_year: 2021,
        last_year: 2021,
      }),
    ],
    "collective",
  );
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].authorKind, "bench");
  assert.equal(
    parseCguFederalAmendmentRankingRows([rankingRow()], "collective"),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentRankingRows([rankingRow()], "todas"),
    null,
  );
});

function legislatureRow(overrides = {}) {
  return {
    legislature_number: 56,
    legislature_label: "56ª Legislatura da Câmara dos Deputados",
    full_fiscal_year_from: 2020,
    full_fiscal_year_to: 2022,
    author_scope: "person",
    rank_position: 1,
    author_kind: "person",
    author_key: "tito",
    author_name: "TITO",
    author_code: "4072",
    amendment_count: 6,
    committed_amount: 1756799.72,
    effective_paid_amount: 1645872.6,
    first_year: 2020,
    last_year: 2022,
    ranking_amount_stage: "committed",
    methodology_version: "cgu-federal-amendment-legislature-ranking/1.0.0",
    ...overrides,
  };
}

test("série CGU por legislatura mantém janelas, escopos e sequência", () => {
  const rows = parseCguLegislatureRankingRows([
    legislatureRow(),
    legislatureRow({
      rank_position: 2,
      author_key: "afonso florence",
      author_name: "AFONSO FLORENCE",
      author_code: "1111",
      amendment_count: 1,
      committed_amount: 400000,
      effective_paid_amount: 400000,
      first_year: 2021,
      last_year: 2021,
    }),
    legislatureRow({
      author_scope: "collective",
      author_kind: "bench",
      author_key: "bancada da bahia",
      author_name: "BANCADA DA BAHIA",
      author_code: "7106",
      amendment_count: 3,
      committed_amount: 4416350,
      effective_paid_amount: 4416350,
      first_year: 2020,
      last_year: 2022,
    }),
  ]);
  assert.notEqual(rows, null);
  const groups = groupCguLegislatureRankings(rows);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].legislatureNumber, 56);
  assert.equal(groups[0].people.length, 2);
  assert.equal(groups[0].collectives.length, 1);
  assert.equal(groups[0].people[0].committedAmount, "1756799.72");
});

test("série CGU por legislatura rejeita respostas incoerentes", () => {
  assert.equal(
    parseCguLegislatureRankingRows([
      legislatureRow({ first_year: 2019 }),
    ]),
    null,
    "ano fora da janela de anos completos da legislatura",
  );
  assert.equal(
    parseCguLegislatureRankingRows([
      legislatureRow(),
      legislatureRow({ rank_position: 3, author_key: "outro" }),
    ]),
    null,
    "posições fora de sequência dentro da mesma legislatura e escopo",
  );
  assert.equal(
    parseCguLegislatureRankingRows([
      legislatureRow({ author_scope: "collective" }),
    ]),
    null,
    "pessoa não pode aparecer no escopo coletivo",
  );
  assert.equal(
    parseCguLegislatureRankingRows([
      legislatureRow({ ranking_amount_stage: "destination" }),
    ]),
    null,
    "estágio de destinação pertence ao Transferegov, nunca à série CGU",
  );
});

test("estágio do ranking é sempre o empenhado declarado, sem mistura", () => {
  assert.equal(
    parseCguFederalAmendmentRankingRows(
      [rankingRow({ ranking_amount_stage: "paid" })],
      "person",
    ),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentRankingRows(
      [rankingRow({ first_year: 2024, last_year: 2023 })],
      "person",
    ),
    null,
  );
});

test("execução federal filtra autor e ano somente dentro do acervo publicado", () => {
  const amendments = [
    executionRow(),
    executionRow({
      fiscal_year: 2022,
      amendment_code: "202240720004",
      source_row_number: 70001,
    }),
    executionRow({
      fiscal_year: 2023,
      amendment_code: "202311110001",
      author_key: "afonso florence",
      author_name: "AFONSO FLORENCE",
      author_code: "1111",
      source_row_number: 70002,
    }),
  ];
  const parsed = parseCguFederalAmendmentRows(amendments);
  assert.notEqual(parsed, null);

  const filters = resolveCguExecutionFilters("tito", "2023", parsed);
  assert.deepEqual(filters, { authorKey: "tito", fiscalYear: 2023 });
  assert.deepEqual(
    filterCguExecutionAmendments(parsed, filters).map((row) => row.amendmentCode),
    ["202340720005"],
  );
});

test("filtro repetido ou fora do acervo não fabrica ausência", () => {
  const parsed = parseCguFederalAmendmentRows([executionRow()]);
  assert.notEqual(parsed, null);
  assert.deepEqual(resolveCguExecutionFilters(["tito"], "2023", parsed), {
    authorKey: null,
    fiscalYear: 2023,
  });
  assert.deepEqual(resolveCguExecutionFilters("desconhecido", "1999", parsed), {
    authorKey: null,
    fiscalYear: null,
  });
});

test("contador da consulta usa singular e plural em português", () => {
  assert.equal(
    cguExecutionResultCountCopy(1),
    "1 linha oficial encontrada com estes filtros.",
  );
  assert.equal(
    cguExecutionResultCountCopy(2),
    "2 linhas oficiais encontradas com estes filtros.",
  );
});

test("ranking cria atalho seguro para as linhas oficiais do parlamentar", () => {
  assert.equal(
    cguExecutionAuthorHref("tito & comissão"),
    "/recursos?origem=federal-execucao&autor=tito%20%26%20comiss%C3%A3o",
  );
  assert.match(resourcesPage, /Ver linhas oficiais deste parlamentar/);
});

test("página oferece investigação por parlamentar e ano e explica 2023", () => {
  assert.match(resourcesPage, /name="autor"/);
  assert.match(resourcesPage, /name="ano"/);
  assert.match(resourcesPage, /2023 é um ano de transição/);
  assert.match(resourcesPage, /não\s+entra no ranking por legislatura/);
  assert.match(resourcesPage, /cguExecutionResultCountCopy\(filteredAmendments\.length\)/);
});
