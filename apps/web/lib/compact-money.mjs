// Leitura rápida de valores grandes ("R$ 1,05 bilhão"). Só para exibição: o
// valor exato (decimal em texto) continua ao lado, e nenhuma conta usa isto.
const UNITS = [
  [1e9, "bilhão", "bilhões"],
  [1e6, "milhão", "milhões"],
  [1e3, "mil", "mil"],
];

function roundToUnit(absolute, size) {
  const scaled = absolute / size;
  const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
  return { digits, rounded: Number(scaled.toFixed(digits)) };
}

export function formatBrlCompact(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  const sign = amount < 0 ? "-" : "";
  const absolute = Math.abs(amount);
  for (const [index, unit] of UNITS.entries()) {
    if (absolute < unit[0]) continue;
    let [size, singular, plural] = unit;
    let { digits, rounded } = roundToUnit(absolute, size);
    // 999,95 milhões arredonda para 1.000: sobe para a unidade seguinte.
    if (rounded >= 1000 && index > 0) {
      [size, singular, plural] = UNITS[index - 1];
      ({ digits, rounded } = roundToUnit(absolute, size));
    }
    const text = rounded.toLocaleString("pt-BR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
    // Singular ou plural pelo número já arredondado, que é o que se lê.
    return `${sign}R$ ${text} ${rounded < 2 ? singular : plural}`;
  }
  return `${sign}R$ ${absolute.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}
