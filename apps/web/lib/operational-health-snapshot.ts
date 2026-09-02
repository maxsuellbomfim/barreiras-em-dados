import "server-only";

import { getMunicipalCouncillors } from "./councillors";
import { getExecutiveProfiles } from "./executive-profiles";
import { getPublicFinanceCoverage } from "./finance-coverage";
import { getIntegralGazetteEditions } from "./integral-gazette-documents";
import {
  buildOperationalHealth,
  combineRepresentationHealthProbes,
  type OperationalHealth,
  type OperationalProbe,
} from "./operational-health.mjs";
import { getFederalRepresentatives } from "./representatives";
import { getStateRepresentatives } from "./state-representatives";

function availableRecords(records: readonly unknown[]): OperationalProbe {
  return { state: "available", records: records.length };
}

export async function getOperationalHealthSnapshot(): Promise<OperationalHealth> {
  const [diary, finance, councillors, executive, state, federal] =
    await Promise.all([
      getIntegralGazetteEditions({ pageSize: 1 }),
      getPublicFinanceCoverage(),
      getMunicipalCouncillors(),
      getExecutiveProfiles(),
      getStateRepresentatives(),
      getFederalRepresentatives(),
    ]);

  const representatives = combineRepresentationHealthProbes([
    councillors.state === "available"
      ? availableRecords(councillors.councillors)
      : { state: "unavailable" },
    executive.state === "available"
      ? availableRecords(executive.profiles)
      : { state: "unavailable" },
    state.state === "available"
      ? availableRecords(state.representatives)
      : { state: "unavailable" },
    federal.state === "available"
      ? availableRecords(federal.representatives)
      : { state: "unavailable" },
  ]);

  return buildOperationalHealth({
    checkedAt: new Date().toISOString(),
    diary:
      diary.state === "available"
        ? { state: "available", records: diary.editions.length }
        : { state: "unavailable" },
    finance:
      finance.state === "available"
        ? { state: "available", records: finance.rows.length }
        : { state: "unavailable" },
    representatives,
  });
}
