import {
  classifyElectionOutcome,
  electionCycleLabel,
  electionPeriodLabel,
  outcomeLabel,
} from "./representative-election-context.mjs";

function formatVotes(value, voteScope) {
  const suffix = voteScope === "ticket" ? "votos da chapa em Barreiras" : "votos em Barreiras";
  return `${value.toLocaleString("pt-BR")} ${suffix}`;
}

export function buildRepresentativeTrajectory({ currentMandate, electionEvents }) {
  const elections = [...electionEvents]
    .sort(
      (left, right) =>
        left.electionYear - right.electionYear
        || left.turnNumber - right.turnNumber
        || left.office.localeCompare(right.office, "pt-BR"),
    )
    .map((event) => ({
      key: `election-${event.electionYear}-${event.candidateId}-${event.turnNumber}`,
      kind: "election",
      heading: `Candidatura a ${event.office}`,
      period: `${electionCycleLabel(event.electionYear, event.office)} · ${electionPeriodLabel(event.electionYear, event.office)} · ${event.turnNumber}º turno`,
      status: outcomeLabel(classifyElectionOutcome(event.situation)),
      detail: formatVotes(event.votesInBarreiras, event.voteScope),
      sourceLabel: "TSE",
      sourceUrl: event.evidenceUrl,
    }));

  return [
    ...elections,
    {
      key: "current",
      kind: "current",
      heading: currentMandate.office,
      period: currentMandate.period,
      status: currentMandate.status,
      detail: "Situação atual publicada pela fonte oficial",
      sourceLabel: currentMandate.sourceLabel,
      sourceUrl: currentMandate.sourceUrl,
    },
  ];
}
