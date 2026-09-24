const SHA256 = /^[0-9a-f]{64}$/;
const COMMITMENT_KEY = /^O-\d+$/;
const DATE_TEXT = /^\d{2}\/\d{2}\/\d{4}$/;
const MONTH = /^\d{4}-\d{2}$/;
const METHODOLOGY = "commitment-liquidations/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const liquidation = {
    commitmentKey: text(row.commitment_key),
    liquidationDateText: text(row.liquidation_date_text),
    amountText: text(row.amount_text),
    gridArtifactSha256: text(row.grid_artifact_sha256),
    gridMonth: text(row.grid_month),
  };
  if (
    Object.values(liquidation).some((value) => value === null) ||
    !COMMITMENT_KEY.test(liquidation.commitmentKey) ||
    !DATE_TEXT.test(liquidation.liquidationDateText) ||
    !SHA256.test(liquidation.gridArtifactSha256) ||
    !MONTH.test(liquidation.gridMonth) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return liquidation;
}

export function parseCommitmentLiquidationRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function groupLiquidationsByCommitment(liquidations) {
  const grouped = new Map();
  for (const liquidation of liquidations) {
    const current = grouped.get(liquidation.commitmentKey) ?? [];
    current.push(liquidation);
    grouped.set(liquidation.commitmentKey, current);
  }
  return grouped;
}
