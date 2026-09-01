import { getPublicFinanceCoverage } from "../../../lib/finance-coverage";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(): Promise<Response> {
  const result = await getPublicFinanceCoverage();
  return Response.json(result, {
    status: result.state === "available" ? 200 : 503,
    headers: {
      "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
    },
  });
}
