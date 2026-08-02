"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { useFavorites } from "@/components/FavoritesProvider";
import { findWatchGameForTeam, type WatchBoardGame, WATCH_MULTI_MAX } from "@/lib/watch-board-game";
import { fetchClientWatchStatusLines } from "@/lib/watch-live-client";
import type { WatchTeamCard } from "@/lib/watch-team-status";

const POLL_MS = 15_000;

type WatchTeamsGridProps = {
  teams: WatchTeamCard[];
  games?: WatchBoardGame[];
  selectedGameIds?: Set<string>;
  onToggleMultiView?: (teamId: string) => void;
};

export function WatchTeamsGrid({
  teams: initialTeams,
  games = [],
  selectedGameIds,
  onToggleMultiView
}: WatchTeamsGridProps) {
  const { favoriteTeamIds, user } = useFavorites();
  const [teams, setTeams] = useState(initialTeams);

  useEffect(() => {
    setTeams(initialTeams);
  }, [initialTeams]);

  useEffect(() => {
    let cancelled = false;

    async function refreshStatuses() {
      try {
        const byTeam = await fetchClientWatchStatusLines();
        if (cancelled || Object.keys(byTeam).length === 0) {
          return;
        }
        setTeams((current) =>
          current.map((team) =>
            byTeam[team.id] ? { ...team, statusLine: byTeam[team.id] } : team
          )
        );
      } catch {
        // Keep last good status line if MLB blips.
      }
    }

    const id = window.setInterval(refreshStatuses, POLL_MS);
    void refreshStatuses();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const favoriteTeams = teams.filter((team) => favoriteTeamIds.includes(team.id));
  const otherTeams = teams.filter((team) => !favoriteTeamIds.includes(team.id));
  const selectedCount = selectedGameIds?.size ?? 0;

  const networkCard = (
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
  );

  function renderCard(team: WatchTeamCard) {
    const game = findWatchGameForTeam(team.id, games);
    const inView = Boolean(game && selectedGameIds?.has(game.id));
    const canAdd = Boolean(game && onToggleMultiView && (inView || selectedCount < WATCH_MULTI_MAX));

    return (
      <div className="team-watch-card-wrap" key={team.id}>
        <Link className="team-watch-card" href={`/watch/${team.id}`}>
          <span className="team-card-stripe" style={{ background: team.primary }} />
          {team.logoUrl ? <img alt="" src={team.logoUrl} /> : <span className="team-card-fallback">{team.abbreviation}</span>}
          <span>
            <strong>{team.name}</strong>
            <span className="team-watch-status">{team.statusLine ?? "No game today"}</span>
            <span className="team-watch-abbrev">{team.abbreviation}</span>
          </span>
        </Link>
        <div className="team-watch-card-actions">
          {canAdd ? (
            <button
              className={inView ? "watch-multi-toggle active" : "watch-multi-toggle"}
              onClick={() => onToggleMultiView?.(team.id)}
              type="button"
            >
              {inView ? "In view" : "Add"}
            </button>
          ) : null}
          <FavoriteButton kind="team" label={team.name} teamId={team.id} />
        </div>
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
        {(user && favoriteTeams.length > 0 ? otherTeams : teams).map(renderCard)}
        {networkCard}
      </section>
    </>
  );
}
