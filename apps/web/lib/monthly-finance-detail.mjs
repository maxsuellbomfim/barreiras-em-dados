const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SHA256 = /^[0-9a-f]{64}$/;

function text(value) {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value.trim())) {
    return value.trim();
  }
  if (
    typeof value === "number"
    && Number.isFinite(value)
    && Math.abs(value) <= Number.MAX_SAFE_INTEGER
  ) {
    const normalized = String(value);
    return DECIMAL.test(normalized) ? normalized : null;
  }
  return null;
}

function optionalDecimal(value) {
  return value === null ? null : decimal(value);
}

function nonNegativeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function httpsUrl(value) {
  const normalized = text(value);
  return normalized?.startsWith("https://") ? normalized : null;
}

function sha256(value) {
  const normalized = text(value);
  return normalized && SHA256.test(normalized) ? normalized : null;
}

function parseRevenueDocument(value) {
  if (typeof value !== "object" || value === null) return null;
  const documentUrl = httpsUrl(value.document_url);
  const artifactSha256 = sha256(value.artifact_sha256);
  const sourceUrl = httpsUrl(value.source_url);
  const sourceArtifactSha256 = sha256(value.source_artifact_sha256);
  const lineCount = nonNegativeInteger(value.line_count);
  const reportAmount = decimal(value.report_amount);
  if (
    !documentUrl
    || !artifactSha256
    || !sourceUrl
    || !sourceArtifactSha256
    || lineCount === null
    || reportAmount === null
  ) {
    return null;
  }
  return {
    documentUrl,
    artifactSha256,
    sourceUrl,
    sourceArtifactSha256,
    lineCount,
    reportAmount,
  };
}

function parseExpenseDocument(value) {
  if (typeof value !== "object" || value === null) return null;
  const documentUrl = httpsUrl(value.document_url);
  const artifactSha256 = sha256(value.artifact_sha256);
  const sourceUrl = httpsUrl(value.source_url);
  const sourceArtifactSha256 = sha256(value.source_artifact_sha256);
  const committedAmount = decimal(value.committed_amount);
  const liquidatedAmount = decimal(value.liquidated_amount);
  const paidAmount = decimal(value.paid_amount);
  if (
    !documentUrl
    || !artifactSha256
    || !sourceUrl
    || !sourceArtifactSha256
    || committedAmount === null
    || liquidatedAmount === null
    || paidAmount === null
  ) {
    return null;
  }
  return {
    documentUrl,
    artifactSha256,
    sourceUrl,
    sourceArtifactSha256,
    committedAmount,
    liquidatedAmount,
    paidAmount,
  };
}

function parseArray(value, parser) {
  if (!Array.isArray(value)) return null;
  const parsed = [];
  for (const item of value) {
    const result = parser(item);
    if (!result) return null;
    parsed.push(result);
  }
  return parsed;
}

export function periodStartFromSlug(slug) {
  if (typeof slug !== "string") return null;
  const match = /^(\d{4})-(\d{2})$/.exec(slug);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (year < 1900 || year > 2200 || month < 1 || month > 12) return null;
  return `${match[1]}-${match[2]}-01`;
}

export function monthlyFinanceHref(periodStart) {
  if (
    typeof periodStart !== "string"
    || !ISO_DATE.test(periodStart)
    || periodStart.slice(8) !== "01"
    || periodStartFromSlug(periodStart.slice(0, 7)) !== periodStart
  ) {
    return "/financas";
  }
  return `/financas/${periodStart.slice(0, 7)}`;
}

export function monthlyFinanceDocumentSourceCopy(document) {
  let documentHostname = "";
  let sourceHostname = "";
  try {
    documentHostname = new URL(document?.documentUrl).hostname.toLowerCase();
    sourceHostname = new URL(document?.sourceUrl).hostname.toLowerCase();
  } catch {
    // A interface recebe documentos já validados, mas mantém texto neutro por segurança.
  }

  if (
    documentHostname === "e.tcm.ba.gov.br"
    && sourceHostname === "e.tcm.ba.gov.br"
  ) {
    return {
      label: "TCM-BA",
      explanation:
        "Este demonstrativo foi obtido no e-TCM e é mostrado como fonte oficial distinta do portal municipal.",
      documentAction: "Abrir PDF no TCM-BA",
      sourceAction: "Abrir registro no e-TCM",
    };
  }

  return {
    label: "Fonte oficial do documento",
    explanation:
      "O arquivo e a resposta de origem permanecem separados para conferência.",
    documentAction: "Abrir PDF oficial",
    sourceAction: "Abrir resposta da fonte",
  };
}

export function monthlyFinanceStatusCopy(detail) {
  if (!detail) {
    return {
      label: "Dados indisponíveis",
      heading: "Este mês ainda não tem fechamento publicado",
      explanation:
        "A ausência de fechamento não significa receita ou despesa zero. Os documentos precisam ser coletados e validados antes da publicação.",
      canShowDifference: false,
    };
  }

  if (detail.closureStatus === "needs_review") {
    return {
      label: "Requer reconciliação",
      heading: "Este mês ainda tem versões para conferir",
      explanation:
        "Existem versões que precisam de reconciliação. Os documentos continuam visíveis, mas a diferença entre receita e pagamentos permanece indisponível para evitar dupla contagem.",
      canShowDifference: false,
    };
  }

  if (detail.closureStatus === "needs_data") {
    return {
      label: "Dados parciais",
      heading: "Ainda faltam documentos para fechar este mês",
      explanation: `${detail.coverageNote} Nenhum valor ausente é tratado como zero.`,
      canShowDifference: false,
    };
  }

  const difference = Number(detail.operationalDifferenceAmount);
  const heading = difference < 0
    ? "Os pagamentos ficaram acima da receita declarada"
    : difference === 0
      ? "A receita declarada e os pagamentos ficaram iguais"
      : "A receita declarada ficou acima dos pagamentos";
  return {
    label: "Mês comparável",
    heading,
    explanation:
      "A diferença operacional é receita declarada menos pagamentos do mesmo mês. Ela não representa saldo bancário, superávit fiscal nem dinheiro livre em caixa.",
    canShowDifference: true,
  };
}

export function selectMonthlyExpenseReportId(reports, detail) {
  if (
    !Array.isArray(reports)
    || typeof detail !== "object"
    || detail === null
    || detail.expenseReportCount !== 1
  ) {
    return null;
  }

  const matches = reports.filter((report) =>
    typeof report === "object"
    && report !== null
    && typeof report.expenseReportId === "string"
    && report.expenseReportId.trim().length > 0
    && report.fiscalYear === detail.fiscalYear
    && report.periodStart === detail.periodStart
    && report.periodEnd === detail.periodEnd
  );

  return matches.length === 1 ? matches[0].expenseReportId : null;
}

export function parseMonthlyFinanceDetail(row) {
  if (typeof row !== "object" || row === null) return null;
  const closureId = text(row.closure_id);
  const periodStart = text(row.period_start);
  const periodEnd = text(row.period_end);
  const publicBodyName = text(row.public_body_name);
  const coverageNote = text(row.coverage_note);
  const revenueReportCount = nonNegativeInteger(row.revenue_report_count);
  const revenueLineCount = nonNegativeInteger(row.revenue_line_count);
  const expenseReportCount = nonNegativeInteger(row.expense_report_count);
  const revenueDocuments = parseArray(row.revenue_documents, parseRevenueDocument);
  const expenseDocuments = parseArray(row.expense_documents, parseExpenseDocument);
  const status = row.closure_status;
  const fiscalYear = row.fiscal_year;

  if (
    !closureId
    || !periodStart
    || !ISO_DATE.test(periodStart)
    || periodStart.slice(8) !== "01"
    || !periodEnd
    || !ISO_DATE.test(periodEnd)
    || !publicBodyName
    || !coverageNote
    || !Number.isSafeInteger(fiscalYear)
    || revenueReportCount === null
    || revenueLineCount === null
    || expenseReportCount === null
    || !revenueDocuments
    || !expenseDocuments
    || revenueDocuments.length !== revenueReportCount
    || expenseDocuments.length !== expenseReportCount
    || (status !== "operational" && status !== "needs_data" && status !== "needs_review")
    || row.calculation_methodology !== "monthly-finance-closure/1.1.0"
    || row.evidence_methodology !== "public-monthly-finance-detail/1.0.0"
  ) {
    return null;
  }

  const revenueReportAmount = optionalDecimal(row.revenue_report_amount);
  const expensePaidAmount = optionalDecimal(row.expense_paid_amount);
  const expenseCommittedAmount = optionalDecimal(row.expense_committed_amount);
  const expenseLiquidatedAmount = optionalDecimal(row.expense_liquidated_amount);
  const operationalDifferenceAmount = optionalDecimal(row.operational_difference_amount);
  if (
    (row.revenue_report_amount !== null && revenueReportAmount === null)
    || (row.expense_paid_amount !== null && expensePaidAmount === null)
    || (row.expense_committed_amount !== null && expenseCommittedAmount === null)
    || (row.expense_liquidated_amount !== null && expenseLiquidatedAmount === null)
    || (row.operational_difference_amount !== null && operationalDifferenceAmount === null)
    || (status === "operational"
      && (revenueReportCount !== 1
        || expenseReportCount !== 1
        || operationalDifferenceAmount === null))
    || (status === "needs_review"
      && revenueReportCount <= 1
      && expenseReportCount <= 1)
  ) {
    return null;
  }

  return {
    closureId,
    fiscalYear: Number(fiscalYear),
    periodStart,
    periodEnd,
    publicBodyName,
    revenueReportAmount,
    revenueReportCount,
    revenueLineCount,
    expensePaidAmount,
    expenseCommittedAmount,
    expenseLiquidatedAmount,
    expenseReportCount,
    operationalDifferenceAmount,
    closureStatus: status,
    coverageNote,
    calculationMethodology: "monthly-finance-closure/1.1.0",
    revenueDocuments,
    expenseDocuments,
    evidenceMethodology: "public-monthly-finance-detail/1.0.0",
  };
}
