const MONTH_START = /^(\d{4})-(\d{2})-01$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const SHA256 = /^[0-9a-f]{64}$/;

function decimalToCents(value) {
  if (typeof value !== "string") return null;
  const match = DECIMAL.exec(value);
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
  const rounded = (absolute + total / 2n) / total;
  return Number(negative ? -rounded : rounded);
}

function basisPointsToPercent(value) {
  if (value === null) return null;
  const negative = value < 0;
  const absolute = Math.abs(value);
  return `${negative ? "-" : ""}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, "0")}`;
}

function monthStarts(fiscalYear) {
  return Array.from(
    { length: 12 },
    (_, index) => `${fiscalYear}-${String(index + 1).padStart(2, "0")}-01`,
  );
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

function validCategory(category, report) {
  return (
    category &&
    category.expenseReportId === report.expenseReportId &&
    typeof category.expenseCode === "string" &&
    category.expenseCode.trim().length > 0 &&
    typeof category.sourceDescription === "string" &&
    category.sourceDescription.trim().length > 0 &&
    Number.isSafeInteger(category.sourceDescriptionCount) &&
    category.sourceDescriptionCount >= 1 &&
    Number.isSafeInteger(category.lineCount) &&
    category.lineCount >= 1 &&
    category.sourceDescriptionCount <= category.lineCount &&
    decimalToCents(category.paidPeriodAmount) !== null &&
    decimalToCents(category.reportTotalPaidAmount) !== null &&
    decimalToCents(category.aggregatedTotalPaidAmount) !== null &&
    category.methodologyVersion === "public-expense-category-summary/1.0.0"
  );
}

export function buildAnnualExpenseCategories({
  fiscalYear,
  closures,
  reports,
  summariesByReport,
}) {
  if (
    !Number.isSafeInteger(fiscalYear) ||
    fiscalYear < 2021 ||
    fiscalYear > 2200 ||
    !Array.isArray(closures) ||
    !Array.isArray(reports) ||
    !(summariesByReport instanceof Map)
  ) {
    return { state: "unavailable" };
  }

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
  const comparablePeriods = new Set(
    comparableClosures.map((closure) => closure.periodStart),
  );
  const reportsByPeriod = new Map();
  for (const report of reports) {
    if (Number(report?.fiscalYear) !== fiscalYear) continue;
    if (!comparablePeriods.has(report.periodStart)) continue;
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
    if (reportPaidCents === null) return { state: "unavailable" };
    if (reportPaidCents !== closurePaidCents) {
      return {
        state: "conflict",
        periodStart: closure.periodStart,
        reason: "expense_total_mismatch",
      };
    }

    const summary = summariesByReport.get(report.expenseReportId);
    if (summary?.state !== "available" || !Array.isArray(summary.categories) || summary.categories.length === 0) {
      continue;
    }

    const categoriesByCode = new Map();
    let categoryPaidCents = 0n;
    for (const category of summary.categories) {
      if (!validCategory(category, report) || categoriesByCode.has(category.expenseCode)) {
        return { state: "unavailable" };
      }
      const paidCents = decimalToCents(category.paidPeriodAmount);
      const categoryReportTotal = decimalToCents(category.reportTotalPaidAmount);
      const aggregatedTotal = decimalToCents(category.aggregatedTotalPaidAmount);
      if (
        paidCents === null ||
        categoryReportTotal !== reportPaidCents ||
        aggregatedTotal !== reportPaidCents
      ) {
        return {
          state: "conflict",
          periodStart: closure.periodStart,
          reason: "category_total_mismatch",
        };
      }
      categoryPaidCents += paidCents;
      categoriesByCode.set(category.expenseCode, { category, paidCents });
    }
    if (categoryPaidCents !== reportPaidCents) {
      return {
        state: "conflict",
        periodStart: closure.periodStart,
        reason: "category_total_mismatch",
      };
    }

    annualPaidCents += reportPaidCents;
    coveredMonths.set(closure.periodStart, { report, categoriesByCode });
    for (const { category, paidCents } of categoriesByCode.values()) {
      const current = aggregateByCode.get(category.expenseCode) ?? {
        expenseCode: category.expenseCode,
        sourceDescription: category.sourceDescription.trim(),
        descriptions: new Set(),
        descriptionVariationObserved: false,
        lineCount: 0,
        monthCount: 0,
        paidCents: 0n,
      };
      current.sourceDescription = category.sourceDescription.trim();
      current.descriptions.add(category.sourceDescription.trim());
      current.descriptionVariationObserved =
        current.descriptionVariationObserved ||
        category.sourceDescriptionCount > 1 ||
        current.descriptions.size > 1;
      current.lineCount += category.lineCount;
      current.monthCount += 1;
      current.paidCents += paidCents;
      aggregateByCode.set(category.expenseCode, current);
    }
  }

  if (coveredMonths.size === 0 || aggregateByCode.size === 0) {
    return {
      state: "empty",
      comparableMonthCount: comparableClosures.length,
      categoryCoveredMonthCount: 0,
    };
  }

  const periods = monthStarts(fiscalYear);
  const categories = [...aggregateByCode.values()]
    .sort((left, right) => {
      if (left.paidCents === right.paidCents) return left.expenseCode.localeCompare(right.expenseCode);
      return left.paidCents > right.paidCents ? -1 : 1;
    })
    .map((aggregate) => {
      const monthlyValues = periods.map((periodStart) => {
        const covered = coveredMonths.get(periodStart);
        if (!covered) {
          return {
            periodStart,
            paidCents: null,
            documentSourceUrl: null,
            documentArtifactSha256: null,
          };
        }
        const categoryValue = covered.categoriesByCode.get(aggregate.expenseCode);
        return {
          periodStart,
          paidCents: categoryValue?.paidCents ?? 0n,
          documentSourceUrl: covered.report.documentSourceUrl,
          documentArtifactSha256: covered.report.documentArtifactSha256,
        };
      });
      const positiveMaximum = monthlyValues.reduce(
        (maximum, month) => month.paidCents !== null && month.paidCents > maximum ? month.paidCents : maximum,
        0n,
      );
      const paidShareBasisPoints = roundedRatioBasisPoints(aggregate.paidCents, annualPaidCents);
      return {
        expenseCode: aggregate.expenseCode,
        sourceDescription: aggregate.sourceDescription,
        descriptionVariationObserved: aggregate.descriptionVariationObserved,
        lineCount: aggregate.lineCount,
        monthCount: aggregate.monthCount,
        paidAmount: centsToDecimal(aggregate.paidCents),
        paidSharePercent: basisPointsToPercent(paidShareBasisPoints),
        months: monthlyValues.map((month) => ({
          periodStart: month.periodStart,
          paidAmount: month.paidCents === null ? null : centsToDecimal(month.paidCents),
          barBasisPoints:
            month.paidCents === null || positiveMaximum === 0n
              ? null
              : month.paidCents < 0n
                ? null
                : Number((month.paidCents * 10_000n) / positiveMaximum),
          documentSourceUrl: month.documentSourceUrl,
          documentArtifactSha256: month.documentArtifactSha256,
        })),
      };
    });

  return {
    state: "available",
    fiscalYear,
    comparableMonthCount: comparableClosures.length,
    categoryCoveredMonthCount: coveredMonths.size,
    annualPaidAmount: centsToDecimal(annualPaidCents),
    categories,
  };
}
