import { NextResponse } from "next/server";

import { getOperationalHealthSnapshot } from "../../../lib/operational-health-snapshot";

export const dynamic = "force-dynamic";

export async function GET() {
  const health = await getOperationalHealthSnapshot();
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
