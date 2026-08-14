const FIRST_STATE_LOA_YEAR = 2022;

export function stateLoaYears(latestFiscalYear) {
  if (!Number.isInteger(latestFiscalYear) || latestFiscalYear < FIRST_STATE_LOA_YEAR) {
    return [];
  }
  return Array.from(
    { length: latestFiscalYear - FIRST_STATE_LOA_YEAR + 1 },
    (_, index) => latestFiscalYear - index,
  );
}

export function resolveStateLoaYear(value, latestFiscalYear) {
  const availableYears = stateLoaYears(latestFiscalYear);
  if (availableYears.length === 0) return null;
  const raw = Array.isArray(value)
    ? value.length === 1 ? value[0] : null
    : value;
  if (typeof raw !== "string" || !/^\d{4}$/.test(raw)) {
    return latestFiscalYear;
  }
  const parsed = Number(raw);
  return availableYears.includes(parsed) ? parsed : latestFiscalYear;
}
