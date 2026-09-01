const MONTHLY_FAMILIES = [
  {
    key: "monthly-finance",
    title: "Receitas e despesas",
    cadence: "Mensal",
    href: "#finance-coverage-title",
    rowsKey: "financeRows",
    periodKey: "periodStart",
    publishedStatus: "complete",
  },
  {
    key: "obligations",
    title: "Restos a pagar",
    cadence: "Mensal",
    href: "#obligation-document-title",
    rowsKey: "obligationRows",
    periodKey: "periodStart",
    publishedStatus: "published",
  },
  {
    key: "payroll",
    title: "Folha de pagamento",
    cadence: "Mensal",
    href: "#finance-payroll-title",
    rowsKey: "payrollRows",
    periodKey: "referenceMonth",
    publishedStatus: "published",
  },
];

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function latest(values) {
  return values.length > 0 ? [...values].sort().at(-1) ?? null : null;
}

function monthlyFamily(definition, input) {
  const rows = Array.isArray(input[definition.rowsKey])
    ? input[definition.rowsKey]
    : [];
  const classified = new Map();

  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const period = text(row[definition.periodKey]);
    const status = text(row.coverageStatus);
    if (!period || !status) continue;
    const body = definition.key === "monthly-finance"
      ? text(row.publicBodyName) ?? "prefeitura"
      : "prefeitura";
    const key = `${body}:${period}`;
    const previous = classified.get(key);
    classified.set(
      key,
      previous === definition.publishedStatus ? previous : status,
    );
  }

  const entries = [...classified.entries()];
  const observed = entries.filter(([, status]) => status === definition.publishedStatus);
  const observedPeriods = observed.length;
  const classifiedPeriods = entries.length;
  const gapPeriods = classifiedPeriods - observedPeriods;

  return {
    key: definition.key,
    title: definition.title,
    cadence: definition.cadence,
    href: definition.href,
    observedPeriods,
    classifiedPeriods,
    gapPeriods,
    latestObservedPeriod: latest(
      observed.map(([key]) => key.slice(key.lastIndexOf(":") + 1)),
    ),
    state: classifiedPeriods === 0
      ? "unavailable"
      : gapPeriods === 0
        ? "complete"
        : "partial",
  };
}

function observedFamily({ key, title, cadence, href, periods }) {
  const uniquePeriods = [...new Set(periods.filter(Boolean))];
  return {
    key,
    title,
    cadence,
    href,
    observedPeriods: uniquePeriods.length,
    classifiedPeriods: null,
    gapPeriods: null,
    latestObservedPeriod: latest(uniquePeriods),
    state: uniquePeriods.length > 0 ? "observed" : "unavailable",
  };
}

export function buildFinanceFamilyCoverage(input) {
  const safeInput = input && typeof input === "object" ? input : {};
  const monthly = MONTHLY_FAMILIES.map((definition) =>
    monthlyFamily(definition, safeInput),
  );
  const fiscalDocuments = Array.isArray(safeInput.fiscalDocuments)
    ? safeInput.fiscalDocuments
    : [];
  const uniqueFiscalDocuments = new Map();
  for (const document of fiscalDocuments) {
    if (!document || typeof document !== "object") continue;
    const resource = text(document.sourceResource);
    if (resource !== "rreo" && resource !== "rgf") continue;
    const period = text(document.referenceDate) ??
      (Number.isSafeInteger(document.fiscalYear) ? String(document.fiscalYear) : null);
    if (period) uniqueFiscalDocuments.set(`${resource}:${period}`, period);
  }
  const fiscal = observedFamily({
    key: "fiscal-statements",
    title: "RREO e RGF",
    cadence: "Bimestral e quadrimestral",
    href: "#fiscal-document-title",
    periods: [...uniqueFiscalDocuments.values()],
  });

  const siconfiYears = Array.isArray(safeInput.siconfiYears)
    ? safeInput.siconfiYears
    : [];
  const annual = observedFamily({
    key: "annual-accounts",
    title: "Contas anuais no Tesouro",
    cadence: "Anual",
    href: "#siconfi-annual-title",
    periods: siconfiYears.flatMap((year) =>
      year && typeof year === "object" && Number.isSafeInteger(year.fiscalYear)
        ? [String(year.fiscalYear)]
        : [],
    ),
  });

  return [...monthly, fiscal, annual];
}
