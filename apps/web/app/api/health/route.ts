import { NextResponse } from "next/server";

import { getMunicipalCouncillors } from "../../../lib/councillors";
import { getPublicFinanceCoverage } from "../../../lib/finance-coverage";
import { buildOperationalHealth } from "../../../lib/operational-health.mjs";
import { getOfficialDiaryCatalog } from "../../../lib/official-diary-catalog";

export const dynamic = "force-dynamic";

export async function GET() {
  const [diary, finance, representatives] = await Promise.all([
    getOfficialDiaryCatalog(),
    getPublicFinanceCoverage(),
    getMunicipalCouncillors(),
  ]);
  const health = buildOperationalHealth({
    checkedAt: new Date().toISOString(),
    diary:
      diary.state === "available"
        ? { state: "available", records: diary.entries.length }
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
  return NextResponse.json(
    health,
    {
      status: health.httpStatus,
      headers: {
        "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
      },
    },
  );
}
