export type TrajectoryCurrentMandate = Readonly<{
  office: string;
  period: string;
  status: string;
  sourceLabel: string;
  sourceUrl: string;
}>;

export type TrajectoryElectionEvent = Readonly<{
  electionYear: number;
  turnNumber: number;
  office: string;
  candidateId: string;
  situation: string | null;
  votesInBarreiras: number;
  voteScope: "person" | "ticket";
  evidenceUrl: string;
}>;

export type RepresentativeTrajectoryEvent = Readonly<{
  key: string;
  kind: "election" | "current";
  heading: string;
  period: string;
  status: string;
  detail: string;
  sourceLabel: string;
  sourceUrl: string;
}>;

export function buildRepresentativeTrajectory(input: Readonly<{
  currentMandate: TrajectoryCurrentMandate;
  electionEvents: readonly TrajectoryElectionEvent[];
}>): readonly RepresentativeTrajectoryEvent[];
