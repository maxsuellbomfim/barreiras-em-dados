import { getPublicPropertyRentals, rentalYear, serializePropertyRentalsCsv } from "../../../../lib/property-rentals.mjs";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const headers = { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff" };

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const currentYear = new Date().getFullYear();
  const yearText = params.get("ano");
  if (
    [...params.keys()].some((key) => key !== "ano") ||
    !yearText ||
    !/^\d{4}$/.test(yearText) ||
    rentalYear(yearText, currentYear) !== Number(yearText)
  ) {
    return new Response("Ano inválido. Volte à página de aluguéis e escolha o ano.\n", {
      status: 400,
      headers: { ...headers, "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  const year = Number(yearText);
  const result = await getPublicPropertyRentals(year);
  if (result.state !== "available") {
    return new Response(
      "Não foi possível montar a planilha agora. Isso não significa que não haja aluguéis.\n",
      { status: 503, headers: { ...headers, "Content-Type": "text/plain; charset=utf-8" } },
    );
  }
  return new Response(serializePropertyRentalsCsv(year, result), {
    headers: {
      ...headers,
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="alugueis-prefeitura-barreiras-${year}.csv"`,
    },
  });
}
