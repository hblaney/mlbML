"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { useFavorites } from "@/components/FavoritesProvider";
import type { Team, TeamStat } from "@/lib/data";
import type { FavoritePlayer } from "@/lib/favorites";
import { getTeamLogoUrl } from "@/lib/team-media";
import type { TeamStanding } from "@/lib/standings";

type PlayerResult = FavoritePlayer;

function formatRunDifferential(value: number) {
  return value > 0 ? `+${value}` : `${value}`;
}

function statValue(stats: FavoritePlayer["hitting"], key: string) {
  return stats?.[key] ?? "-";
}

export function FavoritesClient({
  teams,
  teamStats,
  standings
}: {
  teams: Team[];
  teamStats: TeamStat[];
  standings: TeamStanding[];
}) {
  const { user, favoriteTeamIds, favoritePlayers } = useFavorites();
  const [query, setQuery] = useState("");
  const [playerResults, setPlayerResults] = useState<PlayerResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const teamById = useMemo(() => new Map(teams.map((team) => [team.id, team])), [teams]);
  const standingsByTeamId = useMemo(
    () => new Map(standings.map((standing) => [standing.teamId, standing])),
    [standings]
  );
  const statsByTeamId = useMemo(() => new Map(teamStats.map((stat) => [stat.teamId, stat])), [teamStats]);

  const favoriteTeamRows = favoriteTeamIds
    .map((teamId) => {
      const team = teamById.get(teamId);
      if (!team) {
        return null;
      }

      return {
        team,
        standing: standingsByTeamId.get(teamId),
        stats: statsByTeamId.get(teamId)
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);

  const normalizedQuery = query.trim().toLowerCase();

  const matchingTeams = teams.filter((team) => {
    if (!normalizedQuery) {
      return false;
    }

    return [team.name, team.shortName, team.abbreviation, team.id].some((value) =>
      value.toLowerCase().includes(normalizedQuery)
    );
  });

  async function searchPlayers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (normalizedQuery.length < 2) {
      setPlayerResults([]);
      setSearched(false);
      return;
    }

    setSearching(true);
    setSearched(true);

    try {
      const response = await fetch(`/api/player-search?q=${encodeURIComponent(normalizedQuery)}`);
      const data = (await response.json()) as { players?: PlayerResult[] };
      setPlayerResults(data.players ?? []);
    } finally {
      setSearching(false);
    }
  }

  if (!user) {
    return (
      <section className="panel">
        <p className="eyebrow">Favorites</p>
        <h2>Log in to save teams and players</h2>
        <p className="muted">Create a local account to track favorite teams and player stat snapshots.</p>
        <Link className="button" href="/login">
          Log in
        </Link>
      </section>
    );
  }

  return (
    <>
      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Add favorites</p>
            <h2>Search Teams or Players</h2>
          </div>
        </div>
        <form className="player-search-form" onSubmit={searchPlayers}>
          <input
            className="input"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Dodgers, Judge, Skenes..."
            type="search"
            value={query}
          />
          <button className="button" type="submit">
            Search
          </button>
        </form>
        {searching ? <p className="muted">Searching...</p> : null}
        {normalizedQuery.length >= 2 && matchingTeams.length > 0 ? (
          <div className="favorites-search-results">
            <p className="muted">Teams</p>
            <div className="favorites-team-list">
              {matchingTeams.map((team) => (
                <div className="favorites-team-row" key={team.id}>
                  <span className="dot" style={{ background: team.primary }} />
                  <strong>{team.name}</strong>
                  <FavoriteButton kind="team" label={team.name} teamId={team.id} />
                </div>
              ))}
            </div>
          </div>
        ) : null}
        {searched && !searching && playerResults.length > 0 ? (
          <div className="favorites-search-results">
            <p className="muted">Players</p>
            <div className="player-grid compact">
              {playerResults.map((player) => (
                <article className="player-card" key={player.id}>
                  <img alt={player.name} src={player.headshotUrl} />
                  <div className="player-card-body">
                    <div className="player-card-header">
                      <p className="card-kicker">{player.team}</p>
                      <FavoriteButton kind="player" player={player} />
                    </div>
                    <h3>{player.name}</h3>
                    <p className="muted">{player.position}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        ) : null}
        {searched && !searching && normalizedQuery.length >= 2 && matchingTeams.length === 0 && playerResults.length === 0 ? (
          <p className="muted">No matching teams or players.</p>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Saved teams</p>
            <h2>Favorite Teams</h2>
          </div>
          <span>{favoriteTeamRows.length} teams</span>
        </div>
        {favoriteTeamRows.length === 0 ? (
          <p className="muted">Star teams from Home, Stats, or Watch to build your board.</p>
        ) : (
          <div className="favorites-team-grid">
            {favoriteTeamRows.map(({ team, standing, stats }) => (
              <article className="favorite-team-card" key={team.id}>
                <div className="favorite-team-card-top">
                  {getTeamLogoUrl(team.id) ? <img alt="" src={getTeamLogoUrl(team.id)!} /> : null}
                  <div>
                    <h3>{team.name}</h3>
                    <p className="muted">{team.abbreviation}</p>
                  </div>
                  <FavoriteButton kind="team" label={team.name} teamId={team.id} />
                </div>
                <div className="stat-strip compact">
                  <div>
                    <p className="muted">Record</p>
                    <strong>{standing ? `${standing.wins}-${standing.losses}` : "-"}</strong>
                  </div>
                  <div>
                    <p className="muted">Run Diff</p>
                    <strong>{standing ? formatRunDifferential(standing.runDifferential) : "-"}</strong>
                  </div>
                  <div>
                    <p className="muted">Last 10</p>
                    <strong>{standing?.last10 ?? "-"}</strong>
                  </div>
                  <div>
                    <p className="muted">Div Rank</p>
                    <strong>{standing?.divisionRank ?? "-"}</strong>
                  </div>
                </div>
                {stats ? (
                  <p className="muted">
                    wRC+ {stats.wrcPlus} · Starter ERA {stats.starterEra.toFixed(2)} · Elo {stats.elo}
                  </p>
                ) : null}
                <Link className="button secondary" href={`/watch/${team.id}`}>
                  Watch stream
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Saved players</p>
            <h2>Favorite Players</h2>
          </div>
          <span>{favoritePlayers.length} players</span>
        </div>
        {favoritePlayers.length === 0 ? (
          <p className="muted">Star players from Stats search to save their latest stat snapshot.</p>
        ) : (
          <div className="player-grid">
            {favoritePlayers.map((player) => (
              <article className="player-card" key={player.id}>
                <img alt={player.name} src={player.headshotUrl} />
                <div className="player-card-body">
                  <div className="player-card-header">
                    <p className="card-kicker">{player.team}</p>
                    <FavoriteButton kind="player" player={player} />
                  </div>
                  <h3>{player.name}</h3>
                  <p className="muted">
                    {player.position}
                    {player.number ? ` · #${player.number}` : ""}
                  </p>
                  <div className="player-stat-grid">
                    <span>AVG {statValue(player.hitting, "avg")}</span>
                    <span>OPS {statValue(player.hitting, "ops")}</span>
                    <span>HR {statValue(player.hitting, "homeRuns")}</span>
                    <span>RBI {statValue(player.hitting, "rbi")}</span>
                    <span>ERA {statValue(player.pitching, "era")}</span>
                    <span>WHIP {statValue(player.pitching, "whip")}</span>
                    <span>K {statValue(player.pitching, "strikeOuts")}</span>
                    <span>IP {statValue(player.pitching, "inningsPitched")}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
