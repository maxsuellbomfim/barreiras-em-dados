import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  getPublicPayrollCompensationDistribution,
  getPublicNonpayrollWorkforceCoverage,
  getPublicPayrollRegimeBreakdown,
  getPublicPayrollCoverage,
  getPublicPayrollMonths,
  payrollCompensationMatchesMonth,
  payrollRegimeBreakdownMatchesMonth,
  parsePublicPayrollCompensationRow,
  parsePublicNonpayrollWorkforceCoverageRow,
  parsePublicPayrollCoverageRow,
  parsePublicPayrollRegimeRow,
  parsePublicPayrollRow,
  summarizePublicPayrollYears,
} from "../../apps/web/lib/public-payroll.mjs";

const validRow = {
  reference_month: "2026-07-01",
  public_body_name: "Prefeitura Municipal de Barreiras",
  employee_count: 8184,
  gross_amount: 34971971.48,
  deduction_amount: 10422982.78,
  net_amount: 24548988.7,
  subtotal_count: 133,
  source_url:
    "https://barreiras.mtransparente.com.br/admin/data/folha-julho.pdf",
  artifact_sha256:
    "411cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8",
  source_retrieved_at: "2026-08-21T13:47:57.202502-03:00",
  parser_version: "payroll-monthly-total/1.0.0",
  document_count: 2,
  source_documents: [
    {
      payroll_cycle: "regular",
      source_url:
        "https://barreiras.mtransparente.com.br/admin/data/folha-julho.pdf",
      artifact_sha256:
        "411cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8",
      source_retrieved_at: "2026-08-21T13:47:57.202502-03:00",
      parser_version: "payroll-report-aggregate/1.2.0",
    },
    {
      payroll_cycle: "thirteenth_advance",
      source_url:
        "https://barreiras.mtransparente.com.br/admin/data/decimo-julho.pdf",
      artifact_sha256:
        "511cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8",
      source_retrieved_at: "2026-08-21T13:48:57.202502-03:00",
      parser_version: "payroll-report-aggregate/1.1.0",
    },
  ],
};

const validCoverageRow = {
  reference_month: "2024-04-01",
  coverage_status: "document_not_found",
  coverage_note:
    "A consulta completa ao catálogo oficial não localizou uma Relação de Servidores para esta competência. Isso não significa gasto zero.",
  catalog_document_count: 0,
  preserved_document_count: 0,
  source_url:
    "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=servidores",
  artifact_sha256: null,
  catalog_checked_at: "2026-08-22T04:00:00.000Z",
  methodology_version: "payroll-coverage/1.0.0",
};

const validNonpayrollCoverageRow = {
  reference_month: "2026-08-01",
  workforce_category: "interns",
  category_label: "Estagiários",
  coverage_status: "document_preserved",
  coverage_note:
    "O PDF oficial foi preservado, mas nenhum total agregado será publicado antes de uma reconciliação determinística.",
  catalog_document_count: 1,
  preserved_document_count: 1,
  source_url:
    "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=servidores",
  artifact_sha256:
    "611cd4f055f0e57cd1b0bc111683798ae0b28d84b7d6013d069cc9ca2a3ed0e8",
  catalog_checked_at: "2026-08-30T04:00:00.000Z",
  methodology_version: "nonpayroll-workforce-coverage/1.0.1",
};

const validRegimeRows = [
  {
    reference_month: "2026-07-01",
    regime_code: "selection_process",
    regime_label: "Processo seletivo",
    employee_count: 3827,
    gross_amount: "8456004.61",
    deduction_amount: "866886.95",
    net_amount: "7589117.66",
    source_document_count: 2,
    methodology_version: "payroll-regime-monthly/1.0.0",
  },
  {
    reference_month: "2026-07-01",
    regime_code: "statutory",
    regime_label: "Estatutários",
    employee_count: 4357,
    gross_amount: "26515966.87",
    deduction_amount: "9556095.83",
    net_amount: "16959871.04",
    source_document_count: 2,
    methodology_version: "payroll-regime-monthly/1.0.0",
  },
];

const validCompensationRows = [
  {
    reference_month: "2026-07-01",
    band_code: "up_to_1500",
    band_label: "Até R$ 1.500",
    employee_count: 3000,
    gross_amount: "3900000.00",
    average_gross_amount: "4273.21",
    maximum_gross_amount: "47318.66",
    methodology_version: "payroll-compensation-monthly/1.0.0",
  },
  {
    reference_month: "2026-07-01",
    band_code: "above_20000",
    band_label: "Acima de R$ 20 mil",
    employee_count: 5184,
    gross_amount: "31071971.48",
    average_gross_amount: "4273.21",
    maximum_gross_amount: "47318.66",
    methodology_version: "payroll-compensation-monthly/1.0.0",
  },
];

test("faixas da folha conservam somente agregados e reconciliam vínculos", () => {
  const rows = validCompensationRows.map(parsePublicPayrollCompensationRow);

  assert.ok(rows.every(Boolean));
  assert.equal(rows[0].bandCode, "up_to_1500");
  assert.equal(rows[1].maximumGrossAmount, "47318.66");
  assert.equal(
    payrollCompensationMatchesMonth(rows, parsePublicPayrollRow(validRow)),
    true,
  );
  const serialized = JSON.stringify(rows).toLowerCase();
  for (const forbidden of ["cpf", "name", "matricula", "cargo", "deduction"]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("faixas da folha rejeitam rótulo e campo extra", () => {
  assert.equal(
    parsePublicPayrollCompensationRow({
      ...validCompensationRows[0],
      band_label: "Faixa inventada",
    }),
    null,
  );
  assert.equal(
    parsePublicPayrollCompensationRow({
      ...validCompensationRows[0],
      nome: "não pode atravessar a API",
    }),
    null,
  );
});

test("faixas da folha consultam somente a RPC pública", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  let requestedUrl = null;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return new Response(JSON.stringify(validCompensationRows), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await getPublicPayrollCompensationDistribution("2026-07-01");
    assert.equal(result.state, "available");
    assert.equal(result.rows.length, 2);
    assert.match(
      requestedUrl,
      /rpc\/get_public_payroll_compensation_distribution$/,
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});

test("detalhamento por vínculo conserva somente categorias oficiais agregadas", () => {
  const rows = validRegimeRows.map(parsePublicPayrollRegimeRow);

  assert.ok(rows.every(Boolean));
  assert.equal(rows[0].regimeCode, "selection_process");
  assert.equal(rows[0].employeeCount, 3827);
  assert.equal(rows[1].grossAmount, "26515966.87");
  assert.equal("name" in rows[0], false);
  assert.equal("cpf" in rows[0], false);
  assert.equal(
    payrollRegimeBreakdownMatchesMonth(rows, parsePublicPayrollRow(validRow)),
    true,
  );
});

test("detalhamento por vínculo rejeita rótulo, aritmética e campo pessoal", () => {
  assert.equal(
    parsePublicPayrollRegimeRow({
      ...validRegimeRows[0],
      regime_label: "Rótulo inventado",
    }),
    null,
  );
  assert.equal(
    parsePublicPayrollRegimeRow({
      ...validRegimeRows[0],
      net_amount: "1.00",
    }),
    null,
  );
  assert.equal(
    parsePublicPayrollRegimeRow({
      ...validRegimeRows[0],
      name: "não pode atravessar a API",
    }),
    null,
  );
});

test("detalhamento por vínculo consulta somente a RPC pública", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  let requestedUrl = null;
  let requestedBody = null;
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedBody = JSON.parse(options.body);
    return new Response(JSON.stringify(validRegimeRows), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await getPublicPayrollRegimeBreakdown("2026-07-01");
    assert.equal(result.state, "available");
    assert.equal(result.rows.length, 2);
    assert.match(requestedUrl, /rpc\/get_public_payroll_regime_breakdown$/);
    assert.deepEqual(requestedBody, { target_reference_month: "2026-07-01" });
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});

test("cobertura da folha conserva ausência e conflito como estados, nunca como zero", () => {
  const absent = parsePublicPayrollCoverageRow(validCoverageRow);
  const conflict = parsePublicPayrollCoverageRow({
    ...validCoverageRow,
    reference_month: "2025-01-01",
    coverage_status: "source_conflict",
    coverage_note:
      "O documento oficial mistura ciclos da folha que não podem ser separados com segurança. Os valores ficam fora do total.",
    catalog_document_count: 1,
    preserved_document_count: 1,
    source_url:
      "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES050225.pdf",
    artifact_sha256:
      "d2345bdb7ccceb1553ba627758a70d74cd7124ef3af77dcc48237047e5190ac9",
  });

  assert.ok(absent);
  assert.equal(absent.coverageStatus, "document_not_found");
  assert.equal(absent.artifactSha256, null);
  assert.ok(conflict);
  assert.equal(conflict.coverageStatus, "source_conflict");
  assert.equal(conflict.preservedDocumentCount, 1);
  assert.equal("amount" in absent, false);
  assert.equal("cpf" in conflict, false);
});

test("cobertura da folha recusa estado, fonte e versão não contratados", () => {
  assert.equal(
    parsePublicPayrollCoverageRow({
      ...validCoverageRow,
      coverage_status: "missing",
    }),
    null,
  );
  assert.equal(
    parsePublicPayrollCoverageRow({
      ...validCoverageRow,
      source_url: "http://inseguro",
    }),
    null,
  );
  assert.equal(
    parsePublicPayrollCoverageRow({
      ...validCoverageRow,
      methodology_version: "payroll-coverage/2.0.0",
    }),
    null,
  );
});

test("cobertura separada não transforma estagiários e terceirizados em folha", () => {
  const preserved = parsePublicNonpayrollWorkforceCoverageRow(
    validNonpayrollCoverageRow,
  );
  const notListed = parsePublicNonpayrollWorkforceCoverageRow({
    ...validNonpayrollCoverageRow,
    workforce_category: "outsourced_workers",
    category_label: "Terceirizados",
    coverage_status: "not_listed",
    coverage_note:
      "O catálogo oficial completo não listou documento desta categoria no mês; isso não significa gasto zero.",
    catalog_document_count: 0,
    preserved_document_count: 0,
    artifact_sha256: null,
  });

  assert.ok(preserved);
  assert.equal(preserved.workforceCategory, "interns");
  assert.equal(preserved.coverageStatus, "document_preserved");
  assert.ok(notListed);
  assert.equal(notListed.categoryLabel, "Terceirizados");
  for (const row of [preserved, notListed]) {
    assert.equal("cpf" in row, false);
    assert.equal("name" in row, false);
    assert.equal("amount" in row, false);
    assert.equal("bankAccount" in row, false);
  }
});

test("cobertura separada recusa categoria, estado, contagem e campos extras", () => {
  assert.equal(
    parsePublicNonpayrollWorkforceCoverageRow({
      ...validNonpayrollCoverageRow,
      workforce_category: "employees",
    }),
    null,
  );
  assert.equal(
    parsePublicNonpayrollWorkforceCoverageRow({
      ...validNonpayrollCoverageRow,
      coverage_status: "published",
    }),
    null,
  );
  assert.equal(
    parsePublicNonpayrollWorkforceCoverageRow({
      ...validNonpayrollCoverageRow,
      coverage_status: "catalogued",
      preserved_document_count: 1,
    }),
    null,
  );
  assert.equal(
    parsePublicNonpayrollWorkforceCoverageRow({
      ...validNonpayrollCoverageRow,
      cpf: "000.000.000-00",
    }),
    null,
  );
});

test("folha publica normaliza centavos e conserva somente totais", () => {
  const row = parsePublicPayrollRow(validRow);

  assert.ok(row);
  assert.equal(row.referenceMonth, "2026-07-01");
  assert.equal(row.employeeCount, 8184);
  assert.equal(row.grossAmount, "34971971.48");
  assert.equal(row.deductionAmount, "10422982.78");
  assert.equal(row.netAmount, "24548988.70");
  assert.equal(row.subtotalCount, 133);
  assert.equal(row.documentCount, 2);
  assert.deepEqual(
    row.sourceDocuments.map((document) => document.payrollCycle),
    ["regular", "thirteenth_advance"],
  );
  assert.equal("people" in row, false);
  assert.equal("cpf" in row, false);
  assert.equal("individualDeductions" in row, false);
});

test("resumo anual soma centavos sem transformar meses ausentes em zero", () => {
  const month = (referenceMonth, grossAmount, deductionAmount, netAmount) => ({
    ...parsePublicPayrollRow(validRow),
    referenceMonth,
    grossAmount,
    deductionAmount,
    netAmount,
  });

  const summaries = summarizePublicPayrollYears([
    month("2026-02-01", "0.20", "0.05", "0.15"),
    month("2026-01-01", "0.10", "0.02", "0.08"),
    month("2025-12-01", "10.00", "2.00", "8.00"),
  ]);

  assert.deepEqual(summaries, [
    {
      year: 2026,
      publishedMonthCount: 2,
      expectedMonthCount: 2,
      isComplete: true,
      grossAmount: "0.30",
      deductionAmount: "0.07",
      netAmount: "0.23",
    },
    {
      year: 2025,
      publishedMonthCount: 1,
      expectedMonthCount: 12,
      isComplete: false,
      grossAmount: "10.00",
      deductionAmount: "2.00",
      netAmount: "8.00",
    },
  ]);
});

test("folha publica recusa total que nao fecha deterministicamente", () => {
  assert.equal(parsePublicPayrollRow({ ...validRow, net_amount: 1 }), null);
});

test("folha publica recusa origem, hash ou parser inesperado", () => {
  assert.equal(parsePublicPayrollRow({ ...validRow, source_url: "http://inseguro" }), null);
  assert.equal(parsePublicPayrollRow({ ...validRow, artifact_sha256: "abc" }), null);
  assert.equal(parsePublicPayrollRow({ ...validRow, parser_version: "outro" }), null);
});

test("folha publica aceita temporariamente a projeção anterior no deploy", () => {
  const legacy = { ...validRow };
  delete legacy.document_count;
  delete legacy.source_documents;
  legacy.parser_version = "payroll-report-aggregate/1.0.0";

  const row = parsePublicPayrollRow(legacy);

  assert.ok(row);
  assert.equal(row.documentCount, 1);
  assert.equal(row.sourceDocuments[0].payrollCycle, "regular");
});

test("folha publica aceita o leiaute compacto validado de fevereiro de 2024", () => {
  const compactHeader = {
    ...validRow,
    reference_month: "2024-02-01",
    employee_count: 4947,
    gross_amount: "23541875.29",
    deduction_amount: "7764830.19",
    net_amount: "15777045.10",
    subtotal_count: 127,
    document_count: 1,
    source_url:
      "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES040324112142.pdf",
    artifact_sha256:
      "a5e7e1b6e13daa57dd1b5c48ed21b6e2251fd285a76ff4091b2231b201ddbc9d",
    source_documents: [
      {
        payroll_cycle: "regular",
        source_url:
          "https://barreiras.mtransparente.com.br/admin/data/SERVIDORES040324112142.pdf",
        artifact_sha256:
          "a5e7e1b6e13daa57dd1b5c48ed21b6e2251fd285a76ff4091b2231b201ddbc9d",
        source_retrieved_at: "2026-08-22T03:00:00.000Z",
        parser_version: "payroll-report-aggregate/1.4.0",
      },
    ],
  };

  const row = parsePublicPayrollRow(compactHeader);

  assert.ok(row);
  assert.equal(row.referenceMonth, "2024-02-01");
  assert.equal(row.employeeCount, 4947);
  assert.equal(row.netAmount, "15777045.10");
  assert.equal(
    row.sourceDocuments[0].parserVersion,
    "payroll-report-aggregate/1.4.0",
  );
});

test("folha publica rejeita componentes duplicados ou sem folha regular", () => {
  const duplicated = {
    ...validRow,
    source_documents: [
      validRow.source_documents[0],
      { ...validRow.source_documents[0] },
    ],
  };
  const withoutRegular = {
    ...validRow,
    document_count: 1,
    source_documents: [validRow.source_documents[1]],
  };

  assert.equal(parsePublicPayrollRow(duplicated), null);
  assert.equal(parsePublicPayrollRow(withoutRegular), null);
});

test("folha publica percorre o historico por cursor sem truncar o mes antigo", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  const requestedBodies = [];
  const monthAt = (offset) => {
    const date = new Date(Date.UTC(2026, 6 - offset, 1));
    return date.toISOString().slice(0, 10);
  };
  const rowAt = (offset) => ({ ...validRow, reference_month: monthAt(offset) });
  const firstPage = Array.from({ length: 24 }, (_, index) => rowAt(index));
  const secondPage = [rowAt(24)];
  let call = 0;

  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = async (_url, options) => {
    requestedBodies.push(JSON.parse(options.body));
    const payload = call++ === 0 ? firstPage : secondPage;
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const result = await getPublicPayrollMonths(25);
    assert.equal(result.state, "available");
    assert.equal(result.months.length, 25);
    assert.deepEqual(requestedBodies, [
      { page_size: 24, before_month: null },
      { page_size: 1, before_month: firstPage.at(-1).reference_month },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});

test("cobertura da folha consulta a projeção pública sem acessar tabelas privadas", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  let requestedUrl = null;
  let requestedBody = null;

  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedBody = JSON.parse(options.body);
    return new Response(JSON.stringify([validCoverageRow]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const result = await getPublicPayrollCoverage(120);
    assert.equal(result.state, "available");
    assert.equal(result.rows.length, 1);
    assert.match(requestedUrl, /rpc\/get_public_payroll_coverage$/);
    assert.deepEqual(requestedBody, { month_limit: 120 });
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});

test("cobertura separada consulta somente a RPC pública", async () => {
  const originalFetch = globalThis.fetch;
  const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
  const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
  let requestedUrl = null;
  let requestedBody = null;

  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_test";
  globalThis.fetch = async (url, options) => {
    requestedUrl = url;
    requestedBody = JSON.parse(options.body);
    return new Response(JSON.stringify([validNonpayrollCoverageRow]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const result = await getPublicNonpayrollWorkforceCoverage(120);
    assert.equal(result.state, "available");
    assert.equal(result.rows.length, 1);
    assert.match(
      requestedUrl,
      /rpc\/get_public_nonpayroll_workforce_coverage$/,
    );
    assert.deepEqual(requestedBody, { month_limit: 120 });
  } finally {
    globalThis.fetch = originalFetch;
    if (originalUrl === undefined) delete process.env.PUBLIC_DATA_SUPABASE_URL;
    else process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
    if (originalKey === undefined) {
      delete process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;
    } else {
      process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
    }
  }
});

test("pagina explica vínculos, descontos e limite da informação", async () => {
  const [page, sources, breakdown, compensation] = await Promise.all([
    readFile(
      new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-sources.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-regime-breakdown.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-compensation.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);

  assert.match(page, /Quanto custa a folha da Prefeitura/);
  assert.match(page, /Um vínculo não representa necessariamente uma pessoa única/);
  assert.match(page, /não é confirmação bancária/);
  assert.match(page, /não usa IA para calcular esses valores/);
  assert.match(page, /processamentos oficiais/);
  assert.match(sources, /Abrir PDF oficial/);
  assert.match(sources, /13º salário final/);
  assert.match(page, /getPublicPayrollRegimeBreakdown/);
  assert.match(breakdown, /Como a folha se divide por vínculo/);
  assert.match(breakdown, /não representa necessariamente uma pessoa\s+única/);
  assert.match(breakdown, /<details/);
  assert.match(compensation, /Em quais faixas estão os proventos brutos/);
  assert.match(compensation, /não representa salário-base/);
  assert.match(compensation, /Maior bruto em uma linha/);
  assert.match(compensation, /<details/);
});

test("pagina mantém o mês mais recente em destaque e recolhe o histórico", async () => {
  const [page, history, sources] = await Promise.all([
    readFile(
      new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-history.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-payroll-sources.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);

  assert.match(page, /getPublicPayrollMonths\(120\)/);
  assert.match(
    page,
    /const previousPayrollMonths = payrollMonths\.slice\(1, FINANCE_OVERVIEW_LIMIT \+ 1\)/,
  );
  assert.match(
    page,
    /const previousPayrollMonthCount = Math\.max\(0, payrollMonths\.length - 1\)/,
  );
  assert.match(
    page,
    /<FinancePayrollHistory\s+months=\{previousPayrollMonths\}/,
  );
  assert.match(history, /Ver meses anteriores da folha/);
  assert.match(history, /months\.map/);
  assert.match(history, /Conferir \{month\.documentCount/);
  assert.match(sources, /Abrir PDF oficial/);
  assert.match(history, /Mês validado por código/);
});

test("pagina separa estagiários e terceirizados sem publicar valores pessoais", async () => {
  const [page, coverage] = await Promise.all([
    readFile(
      new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../../apps/web/app/financas/finance-nonpayroll-workforce-coverage.tsx",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);

  assert.match(page, /getPublicNonpayrollWorkforceCoverage\(120\)/);
  assert.match(page, /FinanceNonpayrollWorkforceCoverage/);
  assert.match(coverage, /Estagiários e terceirizados/);
  assert.match(coverage, /não entram no total da folha regular/);
  assert.match(coverage, /nenhum valor agregado é presumido/);
  assert.match(coverage, /<details/);
  assert.match(coverage, /const NONPAYROLL_OVERVIEW_LIMIT = 6;/);
  assert.match(
    coverage,
    /const recentDocumentedRows = documentedRows\.slice\(0, NONPAYROLL_OVERVIEW_LIMIT\)/,
  );
  assert.match(coverage, /recentDocumentedRows\.map/);
  assert.doesNotMatch(coverage, /\{documentedRows\.map/);
  assert.match(coverage, /\{documentedRows\.length\.toLocaleString/);
});

test("pagina encaminha competências da folha sem total para a cobertura completa", async () => {
  const page = await readFile(
    new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /getPublicPayrollCoverage\(120\)/);
  assert.doesNotMatch(page, /<FinancePayrollCoverage\b/);
  assert.match(page, /payrollCoverageGapCount/);
  assert.match(page, /Isso não significa gasto zero/);
  assert.match(page, /href="\/financas\/cobertura#payroll-matrix-title"/);
});
