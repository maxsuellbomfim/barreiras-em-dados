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

// RPC money is text: JSON numbers would lose cents for sufficiently large totals.
export function parseAnnualFinanceSummaries(rows) {
  if (!Array.isArray(rows)) return null;
  const summaries = [];
  const seen = new Set();
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const year = row.fiscal_year;
    const count = row.comparable_month_count;
    const first = typeof row.first_period_start === "string" ? MONTH_START.exec(row.first_period_start) : null;
    const last = typeof row.last_period_start === "string" ? MONTH_START.exec(row.last_period_start) : null;
    const revenue = decimalToCents(row.revenue_amount);
    const paid = decimalToCents(row.paid_amount);
    const difference = decimalToCents(row.operational_difference_amount);
    if (!Number.isInteger(year) || year < 2000 || year > 2100 || seen.has(year)
      || !Number.isInteger(count) || count < 1 || count > 12
      || !first || !last || Number(first[1]) !== year || Number(last[1]) !== year
      || Number(first[2]) < 1 || Number(last[2]) > 12
      || Number(last[2]) - Number(first[2]) + 1 < count
      || (count === 1 && first[2] !== last[2])
      || revenue === null || paid === null || difference === null
      || revenue - paid !== difference
      || row.is_full_calendar_year !== (count === 12)) return null;
    seen.add(year);
    summaries.push({
      fiscalYear: year, comparableMonthCount: count,
      firstPeriodStart: row.first_period_start, lastPeriodStart: row.last_period_start,
      revenueAmount: row.revenue_amount, paidAmount: row.paid_amount,
      operationalDifferenceAmount: row.operational_difference_amount,
      isFullCalendarYear: row.is_full_calendar_year,
    });
  }
  return summaries.sort((a, b) => b.fiscalYear - a.fiscalYear);
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
