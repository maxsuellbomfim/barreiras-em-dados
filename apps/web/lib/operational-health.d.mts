export type OperationalProbe =
  | Readonly<{ state: "available"; records: number }>
  | Readonly<{ state: "unavailable" }>;

export type OperationalHealth = Readonly<{
  status: "ok" | "degraded" | "unavailable";
  service: "barreiras-em-dados-web";
  stage: "pre-launch";
  checkedAt: string;
  checks: readonly Readonly<{
    key: "diary" | "finance" | "representatives";
    label: string;
    status: "available" | "empty" | "unavailable";
    records: number | null;
  }>[];
  httpStatus: 200 | 503;
}>;

export function combineRepresentationHealthProbes(
  probes: readonly OperationalProbe[],
): OperationalProbe;

export function buildOperationalHealth(input: Readonly<{
  checkedAt: string;
  diary: OperationalProbe;
  finance: OperationalProbe;
  representatives: OperationalProbe;
}>): OperationalHealth;
