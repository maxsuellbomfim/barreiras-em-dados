import type { ApprovedGazetteAct } from "./approved-acts";

export type ExecutiveSnapshot = Readonly<{
  key: string;
  personName: string;
  positionTitle: string;
  positionSymbol: string | null;
  organization: string | null;
  actType: ApprovedGazetteAct["actType"];
  gazetteDate: string | null;
  gazetteUrl: string | null;
  excerpt: string | null;
  artifactSha256: string;
}>;

type ActWithPosition = ApprovedGazetteAct & {
  personName: string;
  positionTitle: string;
};

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/\s+/g, " ")
    .trim();
}

function actDate(act: ApprovedGazetteAct): number {
  return act.gazetteDate ? Date.parse(act.gazetteDate) : Date.parse(act.approvedAt);
}

/**
 * Builds a deterministic, deliberately modest snapshot from approved acts.
 * It is not a complete roster and never infers identity from a name alone:
 * the key includes the normalized position as well as the person name.
 */
export function buildExecutiveSnapshot(
  acts: readonly ApprovedGazetteAct[],
): readonly ExecutiveSnapshot[] {
  const latestByPosition = new Map<string, ActWithPosition>();

  for (const act of acts) {
    if (!act.personName || !act.positionTitle) continue;
    const positionedAct = act as ActWithPosition;
    const key = `${normalize(act.personName)}::${normalize(act.positionTitle)}`;
    const current = latestByPosition.get(key);
    if (!current || actDate(positionedAct) > actDate(current)) {
      latestByPosition.set(key, positionedAct);
    }
  }

  return [...latestByPosition.entries()]
    .sort(([, left], [, right]) => {
      const dateDifference = actDate(right) - actDate(left);
      if (dateDifference !== 0) return dateDifference;
      return left.personName.localeCompare(right.personName, "pt-BR");
    })
    .map(([key, act]) => ({
      key,
      personName: act.personName,
      positionTitle: act.positionTitle,
      positionSymbol: act.positionSymbol,
      organization: act.organization,
      actType: act.actType,
      gazetteDate: act.gazetteDate,
      gazetteUrl: act.gazetteUrl,
      excerpt: act.excerpt,
      artifactSha256: act.artifactSha256,
    }));
}
