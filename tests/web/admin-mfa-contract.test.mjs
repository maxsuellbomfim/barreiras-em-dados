import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const gate = await readFile(
  new URL("../../apps/admin/app/admin-mfa-gate.tsx", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/admin/app/page.tsx", import.meta.url),
  "utf8",
);

test("painel oferece adesão TOTP sem impor bloqueio antes do cadastro", () => {
  assert.match(gate, /getAuthenticatorAssuranceLevel\(\)/);
  assert.match(gate, /nextLevel === "aal2"/);
  assert.match(gate, /mfa\.enroll\(\{[\s\S]*factorType: "totp"/);
  assert.match(gate, /Nesta primeira fase, o acesso[\s\S]*continua disponível/);
  assert.match(page, /<AdminMfaGate client=\{supabase\}/);
});

test("sessões com fator cadastrado só abrem o painel depois do AAL2", () => {
  assert.match(gate, /currentLevel === "aal2"/);
  assert.match(gate, /mfa\.listFactors\(\)/);
  assert.match(gate, /kind: "challenge"/);
  assert.match(gate, /mfa\.challengeAndVerify\(\{/);
  assert.match(gate, /Código inválido ou expirado/);
});

test("segredo TOTP não é enviado a logs ou mensagens de erro", () => {
  assert.doesNotMatch(gate, /console\.(?:log|debug|info|warn|error)/);
  assert.doesNotMatch(gate, /JSON\.stringify\(.*(?:secret|qrCode)/s);
});
