const DOMAINS = [
  ["diary", "Diário Oficial"],
  ["finance", "Finanças municipais"],
  ["representatives", "Representação política"],
];

function checkFor(key, label, probe) {
  if (probe.state !== "available") {
    return { key, label, status: "unavailable", records: null };
  }
  const records = Number.isSafeInteger(probe.records) && probe.records >= 0
    ? probe.records
    : 0;
  return {
    key,
    label,
    status: records > 0 ? "available" : "empty",
    records,
  };
}

export function buildOperationalHealth({
  checkedAt,
  diary,
  finance,
  representatives,
}) {
  const probes = { diary, finance, representatives };
  const checks = DOMAINS.map(([key, label]) =>
    checkFor(key, label, probes[key]),
  );
  const available = checks.filter((check) => check.status === "available").length;
  const status = available === checks.length
    ? "ok"
    : available === 0 && checks.every((check) => check.status === "unavailable")
      ? "unavailable"
      : "degraded";

  return {
    status,
    service: "barreiras-em-dados-web",
    stage: "pre-launch",
    checkedAt,
    checks,
    httpStatus: status === "unavailable" ? 503 : 200,
  };
}
