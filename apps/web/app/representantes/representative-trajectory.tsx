import {
  buildRepresentativeTrajectory,
  type TrajectoryCurrentMandate,
} from "../../lib/representative-trajectory.mjs";
import type { RepresentativeVote } from "../../lib/representative-votes";

export default function RepresentativeTrajectory({
  currentMandate,
  votes,
}: Readonly<{
  currentMandate: TrajectoryCurrentMandate;
  votes: readonly RepresentativeVote[];
}>) {
  const events = buildRepresentativeTrajectory({
    currentMandate,
    electionEvents: votes,
  });

  return (
    <details className="person-trajectory">
      <summary>
        <span>
          <strong>Trajetória pública comprovada</strong>
          <small>
            {votes.length > 0
              ? `${votes.length.toLocaleString("pt-BR")} ${votes.length === 1 ? "registro eleitoral" : "registros eleitorais"} + situação atual`
              : "situação atual; histórico eleitoral ainda sem vínculo aprovado"}
          </small>
        </span>
      </summary>
      <ol>
        {events.map((event) => (
          <li className={`person-trajectory-event person-trajectory-${event.kind}`} key={event.key}>
            <span className="person-trajectory-marker" aria-hidden="true" />
            <div>
              <span className="person-trajectory-period">{event.period}</span>
              <strong>{event.heading}</strong>
              <span className="person-trajectory-status">{event.status}</span>
              <p>{event.detail}</p>
              <a href={event.sourceUrl} target="_blank" rel="noreferrer">
                Conferir na fonte: {event.sourceLabel} ↗
              </a>
            </div>
          </li>
        ))}
      </ol>
      {votes.some((vote) => vote.voteScope === "ticket") ? (
        <p className="person-trajectory-note">
          {votes.find((vote) => vote.voteScope === "ticket")?.scopeNote}
        </p>
      ) : null}
      {votes.length === 0 ? (
        <p className="person-trajectory-note">
          A ausência de evento eleitoral aqui não significa que a pessoa nunca
          foi candidata. Significa apenas que ainda não existe um crosswalk
          aprovado por identificadores oficiais para este perfil.
        </p>
      ) : (
        <p className="person-trajectory-note">
          O cargo disputado e a situação daquele pleito vêm do TSE. A situação
          atual vem da Casa correspondente; uma não substitui a outra.
        </p>
      )}
      <a className="person-trajectory-study-link" href="#vinculo">
        Ver todas as candidaturas votadas em Barreiras →
      </a>
    </details>
  );
}
