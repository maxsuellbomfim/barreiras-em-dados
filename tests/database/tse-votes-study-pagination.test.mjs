import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationUrl = new URL(
  "../../supabase/migrations/20260902220000_tse_votes_server_pagination.sql",
  import.meta.url,
);

test("estudo eleitoral pagina e filtra todo o acervo sem somar turnos", async () => {
  const migration = await readFile(migrationUrl, "utf8");
  assert.match(migration, /get_tse_barreiras_votes_study/i);
  assert.match(migration, /distinct on \(record\.source_record_key\)/i);
  assert.match(migration, /record\.source_record_key is not null/i);
  assert.match(migration, /votes_total/i);

  const database = new PGlite();
  try {
    await database.exec(`
      create role anon nologin;
      create role authenticated nologin;
      create schema api;
      create schema raw;
      grant usage on schema api to anon, authenticated;
      create table raw.raw_records (
        id uuid primary key,
        source_record_key text,
        record_type text not null,
        payload jsonb not null,
        collected_at timestamptz not null
      );
      create index raw_records_source_key_idx
        on raw.raw_records (record_type, source_record_key)
        where source_record_key is not null;
    `);
    await database.exec(migration);
    await database.exec(`
      insert into raw.raw_records (
        id, source_record_key, record_type, payload, collected_at
      ) values
        ('00000000-0000-0000-0000-000000000001', 'vote:2022:1:11', 'tse_votacao_barreiras',
          '{"ano":2022,"turno":1,"cargo":"DEPUTADO FEDERAL","sq_candidato":"11","numero":"1111","nome":"ANA ANTIGA","nome_urna":"ANA","partido":"AA","situacao":"ELEITO","votos_em_barreiras":90,"zonas":2}',
          '2026-08-01 10:00:00+00'),
        ('00000000-0000-0000-0000-000000000002', 'vote:2022:1:11', 'tse_votacao_barreiras',
          '{"ano":2022,"turno":1,"cargo":"DEPUTADO FEDERAL","sq_candidato":"11","numero":"1111","nome":"ÂNGELA ANA","nome_urna":"ÂNGELA","partido":"AA","situacao":"ELEITO","votos_em_barreiras":100,"zonas":2}',
          '2026-09-01 10:00:00+00'),
        ('00000000-0000-0000-0000-000000000003', 'vote:2022:1:12', 'tse_votacao_barreiras',
          '{"ano":2022,"turno":1,"cargo":"DEPUTADO FEDERAL","sq_candidato":"12","numero":"1212","nome":"BRUNO","nome_urna":"BRUNO","partido":"BB","situacao":"NÃO ELEITO","votos_em_barreiras":50,"zonas":2}',
          '2026-09-01 10:00:00+00'),
        ('00000000-0000-0000-0000-000000000004', 'vote:2022:1:13', 'tse_votacao_barreiras',
          '{"ano":2022,"turno":1,"cargo":"DEPUTADO ESTADUAL","sq_candidato":"13","numero":"1313","nome":"CARLA","nome_urna":"CARLA","partido":"CC","situacao":"SUPLENTE","votos_em_barreiras":80,"zonas":2}',
          '2026-09-01 10:00:00+00'),
        ('00000000-0000-0000-0000-000000000005', 'vote:2024:1:14', 'tse_votacao_barreiras',
          '{"ano":2024,"turno":1,"cargo":"PREFEITO","sq_candidato":"14","numero":"14","nome":"DAVI","nome_urna":"DAVI","partido":"DD","situacao":"NÃO ELEITO","votos_em_barreiras":1000,"zonas":2}',
          '2026-09-01 10:00:00+00'),
        ('00000000-0000-0000-0000-000000000006', 'vote:2024:2:15', 'tse_votacao_barreiras',
          '{"ano":2024,"turno":2,"cargo":"PREFEITO","sq_candidato":"15","numero":"15","nome":"ELISA","nome_urna":"ELISA","partido":"EE","situacao":"ELEITO POR MÉDIA","votos_em_barreiras":1200,"zonas":2}',
          '2026-09-01 10:00:00+00');
    `);

    await database.exec("set role anon");
    const latest = await database.query(`
      select * from api.get_tse_barreiras_votes_study(50, 0, null, true, null, null, null, null)
    `);
    const filtered = await database.query(`
      select * from api.get_tse_barreiras_votes_study(1, 0, 2022, false, 'DEPUTADO FEDERAL', 1, 'elected', 'angela')
    `);
    await database.exec("reset role");

    assert.equal(latest.rows.length, 1);
    assert.equal(latest.rows[0].effective_year, 2024);
    assert.equal(Number(latest.rows[0].total_count), 2);
    assert.equal(Number(latest.rows[0].catalog_count), 5);
    assert.equal(latest.rows[0].votes_total, null);
    assert.deepEqual(latest.rows[0].available_years, [2024, 2022]);
    assert.deepEqual(
      latest.rows[0].items.map((item) => [item.candidate_id, item.turn_number]),
      [["15", 2], ["14", 1]],
    );

    assert.equal(Number(filtered.rows[0].total_count), 1);
    assert.equal(Number(filtered.rows[0].elected_count), 1);
    assert.equal(Number(filtered.rows[0].votes_total), 100);
    assert.equal(filtered.rows[0].items[0].display_name, "ÂNGELA ANA");
    assert.equal(filtered.rows[0].groups[0].votes, 100);
  } finally {
    await database.close();
  }
});
