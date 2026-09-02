import "server-only";

import { getMunicipalCouncillors } from "./councillors";
import { getPublicFinanceCoverage } from "./finance-coverage";
import { getIntegralGazetteEditions } from "./integral-gazette-documents";
import {
  buildOperationalHealth,
  type OperationalHealth,
} from "./operational-health.mjs";

export async function getOperationalHealthSnapshot(): Promise<OperationalHealth> {
  const [diary, finance, representatives] = await Promise.all([
    getIntegralGazetteEditions({ pageSize: 1 }),
    getPublicFinanceCoverage(),
    getMunicipalCouncillors(),
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
    representatives:
      representatives.state === "available"
        ? { state: "available", records: representatives.councillors.length }
        : { state: "unavailable" },
  });
}
