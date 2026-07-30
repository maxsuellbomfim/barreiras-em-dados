import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const schemasDirectory = path.resolve(
  "packages",
  "data-contracts",
  "schemas",
);

const files = (await readdir(schemasDirectory))
  .filter((file) => file.endsWith(".schema.json"))
  .sort();

if (files.length === 0) {
  throw new Error("Nenhum JSON Schema encontrado.");
}

const ids = new Set();
for (const file of files) {
  const raw = await readFile(path.join(schemasDirectory, file), "utf8");
  const schema = JSON.parse(raw);

  if (schema.$schema !== "https://json-schema.org/draft/2020-12/schema") {
    throw new Error(`${file}: draft 2020-12 obrigatório.`);
  }
  if (typeof schema.$id !== "string" || schema.$id.length === 0) {
    throw new Error(`${file}: $id obrigatório.`);
  }
  if (ids.has(schema.$id)) {
    throw new Error(`${file}: $id duplicado.`);
  }
  if (typeof schema.title !== "string" || schema.title.length === 0) {
    throw new Error(`${file}: title obrigatório.`);
  }
  ids.add(schema.$id);
}

process.stdout.write(`${files.length} schemas estruturalmente válidos.\n`);
