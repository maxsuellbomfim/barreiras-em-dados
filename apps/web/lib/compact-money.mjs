// Leitura rápida de valores grandes ("R$ 1,05 bilhão"). Só para exibição: o
// valor exato (decimal em texto) continua ao lado, e nenhuma conta usa isto.
const UNITS = [
  [1e9, "bilhão", "bilhões"],
  [1e6, "milhão", "milhões"],
  [1e3, "mil", "mil"],
];

export function formatBrlCompact(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  const sign = amount < 0 ? "-" : "";
  const absolute = Math.abs(amount);
  for (const [size, singular, plural] of UNITS) {
    if (absolute >= size) {
      const scaled = absolute / size;
      const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
      const text = scaled.toLocaleString("pt-BR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: digits,
      });
      const unit = Math.floor(scaled) === 1 && scaled < 2 ? singular : plural;
      return `${sign}R$ ${text} ${unit}`;
    }
  }
  return `${sign}R$ ${absolute.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
