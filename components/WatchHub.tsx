"use client";

import { useEffect, useState } from "react";
import { WatchMultiView, toggleWatchMultiSlot } from "@/components/WatchMultiView";
import { WatchTeamsGrid } from "@/components/WatchTeamsGrid";
import {
  readWatchMultiSlots,
  type WatchBoardGame,
  type WatchMultiSlot,
  writeWatchMultiSlots
} from "@/lib/watch-board-game";
import type { WatchTeamCard } from "@/lib/watch-team-status";

type WatchHubProps = {
  teams: WatchTeamCard[];
  games: WatchBoardGame[];
};

export function WatchHub({ teams, games }: WatchHubProps) {
  const [slots, setSlots] = useState<WatchMultiSlot[]>([]);

  useEffect(() => {
    const saved = readWatchMultiSlots().filter((slot) => games.some((game) => game.id === slot.gameId));
    setSlots(saved);
  }, [games]);

  useEffect(() => {
    writeWatchMultiSlots(slots);
  }, [slots]);

  const selectedGameIds = new Set(slots.map((slot) => slot.gameId));

  return (
    <>
      <WatchMultiView games={games} onChange={setSlots} slots={slots} />
      <WatchTeamsGrid
        games={games}
        onToggleMultiView={(teamId) => setSlots((current) => toggleWatchMultiSlot(current, games, teamId))}
        selectedGameIds={selectedGameIds}
        teams={teams}
      />
    </>
  );
}
