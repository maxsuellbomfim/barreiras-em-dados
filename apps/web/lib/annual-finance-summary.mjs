const MONTH_START = /^(\d{4})-(\d{2})-01$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;

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

export function summarizeAnnualFinances(closures) {
  if (!Array.isArray(closures)) return [];
  const years = new Map();

  for (const closure of closures) {
    if (typeof closure !== "object" || closure === null) return [];
    if (closure.closureStatus !== "operational") continue;
    const match = typeof closure.periodStart === "string"
      ? MONTH_START.exec(closure.periodStart)
      : null;
    const fiscalYear = Number(match?.[1]);
    const month = Number(match?.[2]);
    const revenue = decimalToCents(closure.revenueReportAmount);
    const paid = decimalToCents(closure.expensePaidAmount);
    if (
      !match ||
      month < 1 ||
      month > 12 ||
      fiscalYear !== closure.fiscalYear ||
      revenue === null ||
      paid === null
    ) {
      return [];
    }

    const current = years.get(fiscalYear) ?? {
      months: new Set(),
      periodStarts: [],
      revenue: 0n,
      paid: 0n,
      invalid: false,
    };
    if (current.months.has(month)) current.invalid = true;
    current.months.add(month);
    current.periodStarts.push(closure.periodStart);
    current.revenue += revenue;
    current.paid += paid;
    years.set(fiscalYear, current);
  }

  return [...years.entries()]
    .filter(([, year]) => !year.invalid && year.months.size > 0)
    .sort(([left], [right]) => right - left)
    .map(([fiscalYear, year]) => {
      const periods = [...year.periodStarts].sort();
      const firstPeriodStart = periods[0];
      const lastPeriodStart = periods.at(-1);
      return {
        fiscalYear,
        comparableMonthCount: year.months.size,
        firstPeriodStart,
        lastPeriodStart,
        revenueAmount: centsToDecimal(year.revenue),
        paidAmount: centsToDecimal(year.paid),
        operationalDifferenceAmount: centsToDecimal(year.revenue - year.paid),
        isFullCalendarYear:
          year.months.size === 12 &&
          firstPeriodStart === `${fiscalYear}-01-01` &&
          lastPeriodStart === `${fiscalYear}-12-01`,
      };
    });
}
