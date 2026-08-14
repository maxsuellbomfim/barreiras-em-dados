const profileSources = [
  {
    source: "federal",
    label: "deputados federais da Bahia",
    module: "barreiras_collectors.commands.collect_camara_deputies",
  },
  {
    source: "municipal",
    label: "vereadores de Barreiras",
    module: "barreiras_collectors.commands.collect_vereadores",
  },
  {
    source: "state",
    label: "deputados estaduais da Bahia",
    module: "barreiras_collectors.commands.collect_alba_deputies",
  },
  {
    source: "executive",
    label: "prefeito, vice e secretarias de Barreiras",
    module: "barreiras_collectors.commands.collect_municipal_executive",
  },
];

const allowedScopes = new Set([
  "all",
  "federal",
  "municipal",
  "state",
  "executive",
  "elections",
]);

const scope = process.argv[2] ?? "all";

if (!allowedScopes.has(scope)) {
  process.stderr.write(`Escopo de representação inválido: ${scope}\n`);
  process.exitCode = 2;
} else {
  const collectElections = scope === "all" || scope === "elections";
  const profiles =
    scope === "all"
      ? profileSources
      : profileSources.filter(({ source }) => source === scope);

  process.stdout.write(
    `${JSON.stringify({
      scope,
      profiles,
      collectElections,
      collectPrivateIdentities: collectElections,
    })}\n`,
  );
}
