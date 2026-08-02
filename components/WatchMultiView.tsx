"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StreamEmbed } from "@/components/StreamEmbed";
import { getTeam } from "@/lib/data";
import { getTeamLogoUrl } from "@/lib/team-media";
import type { WatchStreamSource } from "@/lib/watch-streams";
import {
  findWatchGameForTeam,
  type WatchBoardGame,
  type WatchMultiSlot,
  WATCH_MULTI_MAX,
  watchGameLabel
} from "@/lib/watch-board-game";

type StreamBundle = WatchStreamSource & {
  gameId: string;
  title: string;
  teamId: string;
};

type WatchMultiViewProps = {
  games: WatchBoardGame[];
  slots: WatchMultiSlot[];
  onChange: (slots: WatchMultiSlot[]) => void;
};

export function WatchMultiView({ games, slots, onChange }: WatchMultiViewProps) {
  const [streamsByGameId, setStreamsByGameId] = useState<Map<string, StreamBundle>>(new Map());
  const gamesById = useMemo(() => new Map(games.map((game) => [game.id, game])), [games]);

  useEffect(() => {
    for (const slot of slots) {
      if (streamsByGameId.has(slot.gameId)) continue;
      if (!gamesById.has(slot.gameId)) continue;

      const query = new URLSearchParams({ gameId: slot.gameId, teamId: slot.teamId });
      void fetch(`/api/bet-watcher/stream?${query.toString()}`)
        .then((response) => (response.ok ? response.json() : null))
        .then((payload: StreamBundle | null) => {
          if (!payload) return;
          setStreamsByGameId((current) => {
            if (current.has(slot.gameId)) return current;
            const next = new Map(current);
            next.set(slot.gameId, payload);
            return next;
          });
        });
    }
  }, [gamesById, slots, streamsByGameId]);

  function removeSlot(gameId: string) {
    onChange(slots.filter((slot) => slot.gameId !== gameId));
    setStreamsByGameId((current) => {
      const next = new Map(current);
      next.delete(gameId);
      return next;
    });
  }

  function addGame(game: WatchBoardGame, teamId?: string) {
    if (slots.some((slot) => slot.gameId === game.id)) return;
    if (slots.length >= WATCH_MULTI_MAX) return;
    onChange([...slots, { gameId: game.id, teamId: teamId ?? game.homeTeam }]);
  }

  const panels = slots
    .map((slot) => streamsByGameId.get(slot.gameId))
    .filter((item): item is StreamBundle => Boolean(item));

  const available = games.filter((game) => !slots.some((slot) => slot.gameId === game.id));

  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Multi-view</p>
          <h2>Watch up to {WATCH_MULTI_MAX} games</h2>
        </div>
        <span className="muted">
          {slots.length}/{WATCH_MULTI_MAX}
          {slots.length > 0 ? (
            <>
              {" · "}
              <button className="text-button" onClick={() => onChange([])} type="button">
                Clear
              </button>
            </>
          ) : null}
        </span>
      </div>

      {available.length > 0 ? (
        <div className="watch-multi-picker">
          {available.map((game) => (
            <button
              className="watch-multi-chip"
              disabled={slots.length >= WATCH_MULTI_MAX}
              key={game.id}
              onClick={() => addGame(game)}
              type="button"
            >
              + {watchGameLabel(game)}
            </button>
          ))}
        </div>
      ) : null}

      {slots.length === 0 ? (
        <p className="muted">
          Pick games above, or tap <strong>Add</strong> on a team card. Same feeds as the team watch pages.
        </p>
      ) : (
        <div className="multi-stream-grid">
          {slots.map((slot) => {
            const game = gamesById.get(slot.gameId);
            const stream = streamsByGameId.get(slot.gameId);
            const awayLogo = game ? getTeamLogoUrl(game.awayTeam) : null;
            const homeLogo = game ? getTeamLogoUrl(game.homeTeam) : null;
            const title = stream?.title ?? (game ? watchGameLabel(game) : slot.gameId);
            const focusTeam = getTeam(slot.teamId);

            return (
              <article className="multi-stream-card" key={slot.gameId}>
                <div className="multi-stream-head">
                  <div className="multi-stream-logos">
                    {awayLogo ? <img alt="" src={awayLogo} /> : null}
                    {homeLogo ? <img alt="" src={homeLogo} /> : null}
                  </div>
                  <div>
                    <h3>{title}</h3>
                    <div className="multi-stream-actions">
                      <Link href={`/watch/${slot.teamId}`}>{focusTeam.abbreviation} page ↗</Link>
                      <button onClick={() => removeSlot(slot.gameId)} type="button">
                        Remove
                      </button>
                    </div>
                  </div>
                </div>
                {stream ? (
                  <StreamEmbed sources={stream.sources} title={title} />
                ) : (
                  <p className="muted">Loading stream…</p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** Toggle helper used by team cards. */
export function toggleWatchMultiSlot(
  slots: WatchMultiSlot[],
  games: WatchBoardGame[],
  teamId: string
): WatchMultiSlot[] {
  const game = findWatchGameForTeam(teamId, games);
  if (!game) return slots;
  if (slots.some((slot) => slot.gameId === game.id)) {
    return slots.filter((slot) => slot.gameId !== game.id);
  }
  if (slots.length >= WATCH_MULTI_MAX) return slots;
  return [...slots, { gameId: game.id, teamId }];
}
