const MONTH_START = /^(\d{4})-(\d{2})-01$/;
const DECIMAL = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;
const CATEGORY_LIMIT = 5;

function decimalToCents(value) {
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

export function previousMonthStart(periodStart) {
  const match = typeof periodStart === "string" ? MONTH_START.exec(periodStart) : null;
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (year < 1900 || year > 2200 || month < 1 || month > 12) return null;
  const previousYear = month === 1 ? year - 1 : year;
  const previousMonth = month === 1 ? 12 : month - 1;
  if (previousYear < 1900) return null;
  return `${previousYear}-${String(previousMonth).padStart(2, "0")}-01`;
}

export function compareExpenseCategoryMonths(current, previous) {
  if (
    current?.state !== "available" ||
    previous?.state !== "available" ||
    current.categories.length === 0 ||
    previous.categories.length === 0
  ) {
    return { state: "unavailable" };
  }

  const currentTotal = decimalToCents(current.categories[0].reportTotalPaidAmount);
  const previousTotal = decimalToCents(previous.categories[0].reportTotalPaidAmount);
  if (currentTotal === null || previousTotal === null) {
    return { state: "unavailable" };
  }

  const previousByCode = new Map(
    previous.categories.map((category) => [category.expenseCode, category]),
  );
  const categories = [];
  for (const category of current.categories.slice(0, CATEGORY_LIMIT)) {
    const currentPaid = decimalToCents(category.paidPeriodAmount);
    if (currentPaid === null) return { state: "unavailable" };
    const previousCategory = previousByCode.get(category.expenseCode);
    if (!previousCategory) {
      categories.push({
        expenseCode: category.expenseCode,
        sourceDescription: category.sourceDescription,
        currentPaidAmount: centsToDecimal(currentPaid),
        previousPaidAmount: null,
        differenceAmount: null,
      });
      continue;
    }
    const previousPaid = decimalToCents(previousCategory.paidPeriodAmount);
    if (previousPaid === null) return { state: "unavailable" };
    categories.push({
      expenseCode: category.expenseCode,
      sourceDescription: category.sourceDescription,
      currentPaidAmount: centsToDecimal(currentPaid),
      previousPaidAmount: centsToDecimal(previousPaid),
      differenceAmount: centsToDecimal(currentPaid - previousPaid),
    });
  }

  return {
    state: "available",
    currentTotalPaidAmount: centsToDecimal(currentTotal),
    previousTotalPaidAmount: centsToDecimal(previousTotal),
    totalDifferenceAmount: centsToDecimal(currentTotal - previousTotal),
    categories,
  };
}
