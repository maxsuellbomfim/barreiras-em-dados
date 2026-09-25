import type { PublicPayrollMonth } from "../../lib/public-payroll.mjs";
import { formatPayrollMonthTitle } from "./finance-payroll-month-card";

const shortMonth = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  timeZone: "America/Bahia",
});

export function payrollMonthHref(referenceMonth: string): string {
  return `/financas/folha/${referenceMonth.slice(0, 7)}`;
}

function shortMonthLabel(referenceMonth: string): string {
  return shortMonth
    .format(new Date(`${referenceMonth}T12:00:00-03:00`))
    .replace(".", "");
}

// Todo mês publicado fica a um clique: anterior/seguinte e a grade completa
// por ano. Meses sem folha publicada não aparecem como links (não viram zero).
export default function FinancePayrollMonthNav({
  months,
  currentMonth,
}: Readonly<{
  months: readonly PublicPayrollMonth[];
  currentMonth: string;
}>) {
  const ordered = [...months].sort((left, right) =>
    left.referenceMonth.localeCompare(right.referenceMonth),
  );
  const index = ordered.findIndex((month) => month.referenceMonth === currentMonth);
  const previous = index > 0 ? ordered[index - 1] : null;
  const next = index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null;
  const published = new Set(ordered.map((month) => month.referenceMonth));
  const firstYear = Number(ordered[0]?.referenceMonth.slice(0, 4) ?? 0);
  const lastMonth = ordered.at(-1)?.referenceMonth ?? "";
  const lastYear = Number(lastMonth.slice(0, 4));
  // Grade de janeiro a dezembro (no último ano, até o último mês publicado):
  // lacunas aparecem apagadas e explicadas, em vez de sumirem da lista.
  const years = [];
  for (let year = lastYear; year >= firstYear && year > 0; year -= 1) {
    const lastMonthNumber = year === lastYear ? Number(lastMonth.slice(5, 7)) : 12;
    years.push({
      year,
      months: Array.from({ length: lastMonthNumber }, (_, index) =>
        `${year}-${String(index + 1).padStart(2, "0")}-01`,
      ),
    });
  }
  const missingCount = years.reduce(
    (total, entry) =>
      total + entry.months.filter((month) => !published.has(month)).length,
    0,
  );

  return (
    <nav className="finance-payroll-month-nav" aria-label="Meses da folha">
      <div className="finance-payroll-month-steps">
        {previous ? (
          <a href={payrollMonthHref(previous.referenceMonth)} rel="prev">
            ← {formatPayrollMonthTitle(previous.referenceMonth)}
          </a>
        ) : (
          <span aria-hidden="true" />
        )}
        {next ? (
          <a href={payrollMonthHref(next.referenceMonth)} rel="next">
            {formatPayrollMonthTitle(next.referenceMonth)} →
          </a>
        ) : null}
      </div>
      <details className="finance-payroll-month-picker">
        <summary>
          Ver todos os {ordered.length.toLocaleString("pt-BR")} meses publicados
        </summary>
        <div>
          {missingCount > 0 ? (
            <p className="finance-payroll-month-legend">
              Meses apagados ainda não têm folha publicada. Isso não significa
              gasto zero: <a href="/financas/cobertura">veja o motivo na cobertura</a>.
            </p>
          ) : null}
          {years.map(({ year, months: yearMonths }) => (
            <section key={year} aria-label={`Folha de ${year}`}>
              <h3>{year}</h3>
              <ul>
                {yearMonths.map((referenceMonth) => (
                  <li key={referenceMonth}>
                    {published.has(referenceMonth) ? (
                      <a
                        href={payrollMonthHref(referenceMonth)}
                        aria-current={
                          referenceMonth === currentMonth ? "page" : undefined
                        }
                        aria-label={formatPayrollMonthTitle(referenceMonth)}
                      >
                        {shortMonthLabel(referenceMonth)}
                      </a>
                    ) : (
                      <span
                        className="is-missing"
                        aria-label={`${formatPayrollMonthTitle(referenceMonth)}: folha ainda não publicada`}
                        title="Folha ainda não publicada"
                      >
                        {shortMonthLabel(referenceMonth)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </details>
    </nav>
  );
}
