import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PGlite } from "@electric-sql/pglite";

test("resumo anual agrega 69 meses, sem usar o limite da lista recente", async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      create schema api; create schema finance;
      create role anon; create role authenticated;
      grant usage on schema api to anon, authenticated;
      create table finance.monthly_finance_closure_snapshot_state (filter_year smallint);
      create table finance.monthly_finance_closure_snapshot (
        filter_year smallint, fiscal_year smallint, period_start date,
        closure_status text, revenue_report_amount numeric, expense_paid_amount numeric
      );
      insert into finance.monthly_finance_closure_snapshot_state
        select generate_series(2021, greatest(2026, extract(year from now())::integer));
      insert into finance.monthly_finance_closure_snapshot
      select extract(year from month)::smallint, extract(year from month)::smallint, month::date,
        'operational', 100.01, 90.02
      from generate_series(date '2021-01-01', date '2026-09-01', interval '1 month') month;
    `);
    await db.exec(await readFile(new URL(
      "../../supabase/migrations/20261023040301_public_annual_finance_summary.sql", import.meta.url,
    ), "utf8"));
    const query = "select * from api.get_public_annual_finance_summary()";
    const rows = (await db.query(query)).rows;
    assert.deepEqual(rows.map(r => [r.fiscal_year, r.comparable_month_count]),
      [[2026, 9], [2025, 12], [2024, 12], [2023, 12], [2022, 12], [2021, 12]]);
    assert.equal(rows[2].revenue_amount, "1200.12");
    assert.equal(rows[2].paid_amount, "1080.24");
    assert.equal(rows[2].operational_difference_amount, "119.88");
    assert.equal(rows[2].is_full_calendar_year, true);
    assert.equal(rows[0].is_full_calendar_year, false);
    // The truncated global cache must neither limit nor duplicate annual totals.
    await db.exec(`insert into finance.monthly_finance_closure_snapshot
      select 0, fiscal_year, period_start, closure_status, revenue_report_amount, expense_paid_amount
      from finance.monthly_finance_closure_snapshot order by period_start desc limit 24;`);
    assert.deepEqual((await db.query(query)).rows, rows);
    // An ambiguous operational month must not inflate any public total.
    await db.exec(`insert into finance.monthly_finance_closure_snapshot
      values (2024, 2024, '2024-01-01', 'operational', 100.01, 90.02);`);
    await assert.rejects(db.query(query), /inconsistentes/);
    await db.exec(`delete from finance.monthly_finance_closure_snapshot
      where filter_year=2024 and fiscal_year=2024 and period_start='2024-01-01';
      insert into finance.monthly_finance_closure_snapshot
      values (2024, 2024, '2024-01-01', 'operational', 100.01, 90.02),
        (2026, 2026, '2026-10-01', 'needs_data', null, null);`);
    assert.deepEqual((await db.query(query)).rows, rows);
    await db.exec(`update finance.monthly_finance_closure_snapshot
      set revenue_report_amount=null where filter_year=2021 and fiscal_year=2021;`);
    await assert.rejects(db.query(query), /inconsistentes/);
    await db.exec(`update finance.monthly_finance_closure_snapshot
      set revenue_report_amount=100.01 where filter_year=2021 and fiscal_year=2021;`);
    // More than 120 months still produces complete annual aggregates.
    await db.exec(`insert into finance.monthly_finance_closure_snapshot
      select extract(year from month)::smallint, extract(year from month)::smallint, month::date, 'operational', -5.01, 0
      from generate_series(date '2027-01-01', date '2037-12-01', interval '1 month') month;`);
    assert.equal((await db.query(query)).rows.length, 17);
    assert.equal((await db.query(query)).rows[0].revenue_amount, "-60.12");
    await db.exec("set role anon");
    assert.equal((await db.query(query)).rows.length, 17);
    await assert.rejects(db.query("select * from finance.monthly_finance_closure_snapshot"));
    await db.exec("reset role");
    await db.exec("delete from finance.monthly_finance_closure_snapshot_state where filter_year=2021");
    await assert.rejects(db.query(query), /indisponível/);
    await db.exec("insert into finance.monthly_finance_closure_snapshot_state values (2021)");
    await db.exec("delete from finance.monthly_finance_closure_snapshot");
    assert.deepEqual((await db.query(query)).rows, []);
    await db.exec("delete from finance.monthly_finance_closure_snapshot_state");
    await assert.rejects(db.query(query), /indisponível/);
  } finally { await db.close(); }
});
