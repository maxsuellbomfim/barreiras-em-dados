const MONTH_START = /^(\d{4})-(\d{2})-01$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const STATUSES = new Set(["operational", "needs_data", "needs_review"]);

function decimalToCents(value) {
  if (typeof value !== "string") return null;
  const match = DECIMAL.exec(value);
  if (!match) return null;
  const cents = BigInt(match[2]) * 100n + BigInt((match[3] ?? "").padEnd(2, "0"));
  return match[1] === "-" ? -cents : cents;
}

function barBasisPoints(value, maximum) {
  if (value === null || maximum <= 0n) return null;
  return Number((value * 10_000n) / maximum);
}

export function parseFinanceYearSlug(value, currentYear) {
  if (
    typeof value !== "string" ||
    !/^\d{4}$/.test(value) ||
    !Number.isSafeInteger(currentYear)
  ) {
    return null;
  }
  const year = Number(value);
  return year >= 2021 && year <= currentYear ? year : null;
}

export function buildAnnualFinanceTrend(closures, fiscalYear) {
  if (
    !Array.isArray(closures) ||
    !Number.isSafeInteger(fiscalYear) ||
    fiscalYear < 2021 ||
    fiscalYear > 2200
  ) {
    return { state: "unavailable" };
  }

  const byMonth = new Map();
  let maximum = 0n;
  let comparableMonthCount = 0;

  for (const closure of closures) {
    if (typeof closure !== "object" || closure === null) {
      return { state: "unavailable" };
    }
    if (closure.fiscalYear !== fiscalYear) continue;

    const match = typeof closure.periodStart === "string"
      ? MONTH_START.exec(closure.periodStart)
      : null;
    const month = Number(match?.[2]);
    if (
      !match ||
      Number(match[1]) !== fiscalYear ||
      month < 1 ||
      month > 12 ||
      !STATUSES.has(closure.closureStatus) ||
      byMonth.has(month)
    ) {
      return { state: "unavailable" };
    }

    if (closure.closureStatus !== "operational") {
      byMonth.set(month, {
        month,
        periodStart: closure.periodStart,
        closureStatus: closure.closureStatus,
        revenueAmount: null,
        paidAmount: null,
        operationalDifferenceAmount: null,
        revenueCents: null,
        paidCents: null,
      });
      continue;
    }

    const revenueCents = decimalToCents(closure.revenueReportAmount);
    const paidCents = decimalToCents(closure.expensePaidAmount);
    const differenceCents = decimalToCents(closure.operationalDifferenceAmount);
    if (
      revenueCents === null ||
      paidCents === null ||
      differenceCents === null ||
      revenueCents < 0n ||
      paidCents < 0n ||
      revenueCents - paidCents !== differenceCents
    ) {
      return { state: "unavailable" };
    }
    maximum = revenueCents > maximum ? revenueCents : maximum;
    maximum = paidCents > maximum ? paidCents : maximum;
    comparableMonthCount += 1;
    byMonth.set(month, {
      month,
      periodStart: closure.periodStart,
      closureStatus: closure.closureStatus,
      revenueAmount: closure.revenueReportAmount,
      paidAmount: closure.expensePaidAmount,
      operationalDifferenceAmount: closure.operationalDifferenceAmount,
      revenueCents,
      paidCents,
    });
  }

  return {
    state: "available",
    comparableMonthCount,
    months: Array.from({ length: 12 }, (_, index) => {
      const month = index + 1;
      const current = byMonth.get(month);
      if (!current) {
        return {
          month,
          periodStart: `${fiscalYear}-${String(month).padStart(2, "0")}-01`,
          closureStatus: "missing",
          revenueAmount: null,
          paidAmount: null,
          operationalDifferenceAmount: null,
          revenueBarBasisPoints: null,
          paidBarBasisPoints: null,
        };
      }
      return {
        month: current.month,
        periodStart: current.periodStart,
        closureStatus: current.closureStatus,
        revenueAmount: current.revenueAmount,
        paidAmount: current.paidAmount,
        operationalDifferenceAmount: current.operationalDifferenceAmount,
        revenueBarBasisPoints: barBasisPoints(current.revenueCents, maximum),
        paidBarBasisPoints: barBasisPoints(current.paidCents, maximum),
      };
    }),
  };
}
