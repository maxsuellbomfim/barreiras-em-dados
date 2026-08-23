const MONTH_START = /^(\d{4})-(\d{2})-01$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const SHA256 = /^[0-9a-f]{64}$/;
const UNIT_CODE = /^\d{6,8}$/;

function decimalToCents(value) {
  const match = typeof value === "string" ? DECIMAL.exec(value) : null;
  if (!match) return null;
  const cents = BigInt(match[2]) * 100n + BigInt((match[3] ?? "").padEnd(2, "0"));
  return match[1] === "-" ? -cents : cents;
}

function centsToDecimal(value) {
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  return `${negative ? "-" : ""}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}

function roundedRatioBasisPoints(value, total) {
  if (total <= 0n) return null;
  const numerator = value * 10_000n;
  const negative = numerator < 0n;
  const absolute = negative ? -numerator : numerator;
  return Number(negative ? -(absolute + total / 2n) / total : (absolute + total / 2n) / total);
}

function basisPointsToPercent(value) {
  if (value === null) return null;
  const negative = value < 0;
  const absolute = Math.abs(value);
  return `${negative ? "-" : ""}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, "0")}`;
}

function monthStarts(fiscalYear) {
  return Array.from({ length: 12 }, (_, index) =>
    `${fiscalYear}-${String(index + 1).padStart(2, "0")}-01`);
}

function validPeriod(value, fiscalYear) {
  const match = typeof value === "string" ? MONTH_START.exec(value) : null;
  return match !== null && Number(match[1]) === fiscalYear && Number(match[2]) >= 1 && Number(match[2]) <= 12;
}

function validReport(report, fiscalYear) {
  return (
    report &&
    typeof report.expenseReportId === "string" &&
    Number(report.fiscalYear) === fiscalYear &&
    validPeriod(report.periodStart, fiscalYear) &&
    decimalToCents(report.totalPaidPeriodAmount) !== null &&
    typeof report.documentSourceUrl === "string" &&
    report.documentSourceUrl.startsWith("https://") &&
    typeof report.documentArtifactSha256 === "string" &&
    SHA256.test(report.documentArtifactSha256)
  );
}

function canonicalName(value) {
  return value.trim().replace(/\s+/g, " ").toLocaleUpperCase("pt-BR");
}

function validUnit(unit, report) {
  return (
    unit &&
    unit.expenseReportId === report.expenseReportId &&
    typeof unit.budgetUnitCode === "string" &&
    UNIT_CODE.test(unit.budgetUnitCode) &&
    typeof unit.budgetUnitName === "string" &&
    unit.budgetUnitName.trim().length > 0 &&
    Number.isSafeInteger(unit.budgetUnitNameCount) &&
    unit.budgetUnitNameCount === 1 &&
    Number.isSafeInteger(unit.lineCount) &&
    unit.lineCount >= 1 &&
    Number.isSafeInteger(unit.reportLineCount) &&
    unit.reportLineCount >= unit.lineCount &&
    Number.isSafeInteger(unit.allocatedLineCount) &&
    unit.allocatedLineCount === unit.reportLineCount &&
    decimalToCents(unit.paidPeriodAmount) !== null &&
    decimalToCents(unit.reportTotalPaidAmount) !== null &&
    decimalToCents(unit.allocatedTotalPaidAmount) !== null &&
    unit.methodologyVersion === "public-expense-budget-unit-summary/1.0.0"
  );
}

export function buildAnnualExpenseBudgetUnits({ fiscalYear, closures, reports, summariesByReport }) {
  if (
    !Number.isSafeInteger(fiscalYear) || fiscalYear < 2021 || fiscalYear > 2200 ||
    !Array.isArray(closures) || !Array.isArray(reports) || !(summariesByReport instanceof Map)
  ) return { state: "unavailable" };

  const closuresByPeriod = new Map();
  for (const closure of closures) {
    if (Number(closure?.fiscalYear) !== fiscalYear) continue;
    if (!validPeriod(closure.periodStart, fiscalYear) || closuresByPeriod.has(closure.periodStart)) {
      return { state: "unavailable" };
    }
    closuresByPeriod.set(closure.periodStart, closure);
  }
  const comparableClosures = [...closuresByPeriod.values()].filter(
    (closure) => closure.closureStatus === "operational",
  );
  const comparablePeriods = new Set(comparableClosures.map((closure) => closure.periodStart));
  const reportsByPeriod = new Map();
  for (const report of reports) {
    if (Number(report?.fiscalYear) !== fiscalYear || !comparablePeriods.has(report.periodStart)) continue;
    if (!validReport(report, fiscalYear) || reportsByPeriod.has(report.periodStart)) {
      return { state: "unavailable" };
    }
    reportsByPeriod.set(report.periodStart, report);
  }

  const coveredMonths = new Map();
  const aggregateByCode = new Map();
  let annualPaidCents = 0n;

  for (const closure of comparableClosures.sort((left, right) => left.periodStart.localeCompare(right.periodStart))) {
    const closurePaidCents = decimalToCents(closure.expensePaidAmount);
    if (closurePaidCents === null) return { state: "unavailable" };
    const report = reportsByPeriod.get(closure.periodStart);
    if (!report) continue;
    const reportPaidCents = decimalToCents(report.totalPaidPeriodAmount);
    if (reportPaidCents !== closurePaidCents) {
      return { state: "conflict", periodStart: closure.periodStart, reason: "expense_total_mismatch" };
    }
    const summary = summariesByReport.get(report.expenseReportId);
    if (summary?.state !== "available" || !Array.isArray(summary.budgetUnits) || summary.budgetUnits.length === 0) {
      continue;
    }

    const unitsByCode = new Map();
    let unitPaidCents = 0n;
    for (const unit of summary.budgetUnits) {
      if (!validUnit(unit, report) || unitsByCode.has(unit.budgetUnitCode)) return { state: "unavailable" };
      const paidCents = decimalToCents(unit.paidPeriodAmount);
      if (
        paidCents === null ||
        decimalToCents(unit.reportTotalPaidAmount) !== reportPaidCents ||
        decimalToCents(unit.allocatedTotalPaidAmount) !== reportPaidCents
      ) {
        return { state: "conflict", periodStart: closure.periodStart, reason: "unit_total_mismatch" };
      }
      unitPaidCents += paidCents;
      unitsByCode.set(unit.budgetUnitCode, { unit, paidCents });
    }
    if (unitPaidCents !== reportPaidCents) {
      return { state: "conflict", periodStart: closure.periodStart, reason: "unit_total_mismatch" };
    }

    for (const { unit, paidCents } of unitsByCode.values()) {
      const name = unit.budgetUnitName.trim().replace(/\s+/g, " ");
      const current = aggregateByCode.get(unit.budgetUnitCode);
      if (current && canonicalName(current.budgetUnitName) !== canonicalName(name)) {
        return { state: "conflict", periodStart: closure.periodStart, reason: "unit_name_conflict" };
      }
      const aggregate = current ?? {
        budgetUnitCode: unit.budgetUnitCode,
        budgetUnitName: name,
        lineCount: 0,
        monthCount: 0,
        paidCents: 0n,
      };
      aggregate.lineCount += unit.lineCount;
      aggregate.monthCount += 1;
      aggregate.paidCents += paidCents;
      aggregateByCode.set(unit.budgetUnitCode, aggregate);
    }
    annualPaidCents += reportPaidCents;
    coveredMonths.set(closure.periodStart, { report, unitsByCode });
  }

  if (coveredMonths.size === 0 || aggregateByCode.size === 0) {
    return { state: "empty", comparableMonthCount: comparableClosures.length, unitCoveredMonthCount: 0 };
  }

  const periods = monthStarts(fiscalYear);
  const budgetUnits = [...aggregateByCode.values()]
    .sort((left, right) => left.paidCents === right.paidCents
      ? left.budgetUnitCode.localeCompare(right.budgetUnitCode)
      : left.paidCents > right.paidCents ? -1 : 1)
    .map((aggregate) => {
      const monthlyValues = periods.map((periodStart) => {
        const covered = coveredMonths.get(periodStart);
        if (!covered) return { periodStart, paidCents: null, documentSourceUrl: null, documentArtifactSha256: null };
        return {
          periodStart,
          paidCents: covered.unitsByCode.get(aggregate.budgetUnitCode)?.paidCents ?? 0n,
          documentSourceUrl: covered.report.documentSourceUrl,
          documentArtifactSha256: covered.report.documentArtifactSha256,
        };
      });
      const positiveMaximum = monthlyValues.reduce(
        (maximum, month) => month.paidCents !== null && month.paidCents > maximum ? month.paidCents : maximum,
        0n,
      );
      return {
        budgetUnitCode: aggregate.budgetUnitCode,
        budgetUnitName: aggregate.budgetUnitName,
        lineCount: aggregate.lineCount,
        monthCount: aggregate.monthCount,
        paidAmount: centsToDecimal(aggregate.paidCents),
        paidSharePercent: basisPointsToPercent(roundedRatioBasisPoints(aggregate.paidCents, annualPaidCents)),
        months: monthlyValues.map((month) => ({
          periodStart: month.periodStart,
          paidAmount: month.paidCents === null ? null : centsToDecimal(month.paidCents),
          barBasisPoints: month.paidCents === null || positiveMaximum === 0n || month.paidCents < 0n
            ? null : Number((month.paidCents * 10_000n) / positiveMaximum),
          documentSourceUrl: month.documentSourceUrl,
          documentArtifactSha256: month.documentArtifactSha256,
        })),
      };
    });

  return {
    state: "available",
    fiscalYear,
    comparableMonthCount: comparableClosures.length,
    unitCoveredMonthCount: coveredMonths.size,
    annualPaidAmount: centsToDecimal(annualPaidCents),
    budgetUnits,
  };
}
