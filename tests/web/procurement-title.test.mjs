import assert from "node:assert/strict";
import test from "node:test";

import { splitProcurementTitle } from "../../apps/web/lib/procurement-title.mjs";

test("prefixo de plataforma vira etiqueta e o texto fica literal", () => {
  assert.deepEqual(
    splitProcurementTitle("[LICITANET] - CONTRATAÇÃO DE EMPRESA PARA RECOMPOSIÇÃO ASFÁLTICA (CBUQ)"),
    { platform: "Licitanet", text: "CONTRATAÇÃO DE EMPRESA PARA RECOMPOSIÇÃO ASFÁLTICA (CBUQ)", allCaps: true },
  );
  assert.deepEqual(
    splitProcurementTitle("[LICITANET] - Registro de preço para aquisição de medicamentos"),
    { platform: "Licitanet", text: "Registro de preço para aquisição de medicamentos", allCaps: false },
  );
  assert.deepEqual(
    splitProcurementTitle("Locação de imóvel situado à Rua São Desidério"),
    { platform: null, text: "Locação de imóvel situado à Rua São Desidério", allCaps: false },
  );
  assert.equal(splitProcurementTitle("UBS SEDE").allCaps, false);
  assert.equal(splitProcurementTitle(null).text, "");
});
