"use client";

import { FormEvent, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import type { FavoritePlayer } from "@/lib/favorites";

type PlayerResult = {
  id: number;
  name: string;
  number: string | null;
  position: string;
  bats: string | null;
  throws: string | null;
  team: string;
  headshotUrl: string;
  hitting: Record<string, string | number> | null;
  pitching: Record<string, string | number> | null;
};

function statValue(stats: PlayerResult["hitting"], key: string) {
  return stats?.[key] ?? "-";
}

export function PlayerSearch() {
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState<PlayerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function searchPlayers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();

    if (trimmedQuery.length < 2) {
      setPlayers([]);
      setSearched(false);
      return;
    }

    setLoading(true);
    setSearched(true);

    try {
      const response = await fetch(`/api/player-search?q=${encodeURIComponent(trimmedQuery)}`);
      const data = (await response.json()) as { players?: PlayerResult[] };
      setPlayers(data.players ?? []);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">MLB player lookup</p>
          <h2>Player Search</h2>
        </div>
        <span>{players.length} results</span>
      </div>
      <form className="player-search-form" onSubmit={searchPlayers}>
        <input
          className="input"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search any player: Ohtani, Judge, Skenes..."
          type="search"
          value={query}
        />
        <button className="button" type="submit">
          Search
        </button>
      </form>

      {loading ? <p className="muted">Searching MLB player data...</p> : null}
      {!loading && searched && players.length === 0 ? <p className="muted">No players found.</p> : null}

      {players.length > 0 ? (
        <div className="player-grid">
          {players.map((player) => (
            <article className="player-card" key={player.id}>
              <img alt={player.name} src={player.headshotUrl} />
              <div className="player-card-body">
                <div className="player-card-header">
                  <p className="card-kicker">{player.team}</p>
                  <FavoriteButton kind="player" player={player as FavoritePlayer} />
                </div>
                <h3>{player.name}</h3>
                <p className="muted">
                  {player.position}
                  {player.number ? ` · #${player.number}` : ""} · B/T {player.bats ?? "-"} / {player.throws ?? "-"}
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
      ) : null}
    </section>
  );
}
