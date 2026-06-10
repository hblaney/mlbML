"use client";

import Link from "next/link";
import { FavoriteButton } from "@/components/FavoriteButton";
import { useFavorites } from "@/components/FavoritesProvider";
import type { WatchTeamCard } from "@/lib/watch-team-status";

export function WatchTeamsGrid({ teams }: { teams: WatchTeamCard[] }) {
  const { favoriteTeamIds, user } = useFavorites();

  const favoriteTeams = teams.filter((team) => favoriteTeamIds.includes(team.id));
  const otherTeams = teams.filter((team) => !favoriteTeamIds.includes(team.id));

  function renderCard(team: WatchTeamCard) {
    return (
      <div className="team-watch-card-wrap" key={team.id}>
        <Link className="team-watch-card" href={`/watch/${team.id}`}>
          <span className="team-card-stripe" style={{ background: team.primary }} />
          {team.logoUrl ? <img alt="" src={team.logoUrl} /> : <span className="team-card-fallback">{team.abbreviation}</span>}
          <span>
            <strong>{team.name}</strong>
            {team.statusLine ? <span className="team-watch-status">{team.statusLine}</span> : null}
            <span className="team-watch-abbrev">{team.abbreviation}</span>
          </span>
        </Link>
        <FavoriteButton kind="team" label={team.name} teamId={team.id} />
      </div>
    );
  }

  return (
    <>
      {user && favoriteTeams.length > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Your teams</p>
              <h2>Favorite Streams</h2>
            </div>
            <span>{favoriteTeams.length} saved</span>
          </div>
          <div className="team-watch-grid">{favoriteTeams.map(renderCard)}</div>
        </section>
      ) : null}

      <section className="team-watch-grid">
        <div className="team-watch-card-wrap">
          <Link className="team-watch-card network-watch-card" href="/watch/network">
            <span className="team-card-stripe" style={{ background: "#c41230" }} />
            <span className="team-card-fallback">MLBN</span>
            <span>
              <strong>MLB Network</strong>
              <span className="team-watch-abbrev">National</span>
            </span>
          </Link>
        </div>
        {(user && favoriteTeams.length > 0 ? otherTeams : teams).map(renderCard)}
      </section>
    </>
  );
}
