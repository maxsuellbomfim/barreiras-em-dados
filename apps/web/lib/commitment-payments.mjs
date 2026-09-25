const SHA256 = /^[0-9a-f]{64}$/;
const COMMITMENT_KEY = /^O-\d+$/;
const DATE_TEXT = /^\d{2}\/\d{2}\/\d{4}$/;
const MONTH = /^\d{4}-\d{2}$/;
const PAYMENT_ID = /^\d+$/;
const METHODOLOGY = "commitment-payments/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const payment = {
    commitmentKey: text(row.commitment_key),
    paymentId: text(row.payment_id),
    paymentDateText: text(row.payment_date_text),
    amountText: text(row.amount_text),
    gridArtifactSha256: text(row.grid_artifact_sha256),
    gridMonth: text(row.grid_month),
  };
  if (
    Object.values(payment).some((value) => value === null) ||
    !COMMITMENT_KEY.test(payment.commitmentKey) ||
    !PAYMENT_ID.test(payment.paymentId) ||
    !DATE_TEXT.test(payment.paymentDateText) ||
    !SHA256.test(payment.gridArtifactSha256) ||
    !MONTH.test(payment.gridMonth) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    ...payment,
    processNumber: text(row.process_number),
    contractText: text(row.contract_text),
  };
}

export function parseCommitmentPaymentRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function groupPaymentsByCommitment(payments) {
  const grouped = new Map();
  for (const payment of payments) {
    const current = grouped.get(payment.commitmentKey) ?? [];
    current.push(payment);
    grouped.set(payment.commitmentKey, current);
  }
  return grouped;
}
