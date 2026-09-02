const SCOPES = new Set(["current", "historical", "state"]);

export function buildParliamentaryTransferQueryPlan(scope) {
  const selected = SCOPES.has(scope) ? scope : "none";
  return {
    current: selected === "current",
    historical: selected === "historical",
    state: selected === "state",
  };
}
