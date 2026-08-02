"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { useFavorites } from "@/components/FavoritesProvider";
import type { WatchTeamCard } from "@/lib/watch-team-status";

const POLL_MS = 20_000;

export function WatchTeamsGrid({ teams: initialTeams }: { teams: WatchTeamCard[] }) {
  const { favoriteTeamIds, user } = useFavorites();
  const [teams, setTeams] = useState(initialTeams);

  useEffect(() => {
    setTeams(initialTeams);
  }, [initialTeams]);

  useEffect(() => {
    let cancelled = false;

    async function refreshStatuses() {
      try {
        const response = await fetch("/api/watch-status", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = (await response.json()) as {
          teams?: { id: string; statusLine: string | null }[];
        };
        const next = new Map((payload.teams ?? []).map((row) => [row.id, row.statusLine]));
        if (cancelled || next.size === 0) {
          return;
        }
        setTeams((current) =>
          current.map((team) =>
            next.has(team.id) ? { ...team, statusLine: next.get(team.id) ?? null } : team
          )
        );
      } catch {
        // Keep last good status line if MLB/API blips.
      }
    }

    const id = window.setInterval(refreshStatuses, POLL_MS);
    // Immediate refresh after mount so SSR cache can't leave a stale inning up.
    void refreshStatuses();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const favoriteTeams = teams.filter((team) => favoriteTeamIds.includes(team.id));
  const otherTeams = teams.filter((team) => !favoriteTeamIds.includes(team.id));

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
        {(user && favoriteTeams.length > 0 ? otherTeams : teams).map(renderCard)}
        {networkCard}
      </section>
    </>
  );
}
