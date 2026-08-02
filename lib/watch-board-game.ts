import type { GamePrediction } from "./data";
import { getTeam, normalizeTeamId } from "./data";

/** Lightweight board game row for the watch multi-view (client-safe). */
export type WatchBoardGame = {
  id: string;
  awayTeam: string;
  homeTeam: string;
  startsAt: string;
};

export type WatchMultiSlot = {
  gameId: string;
  teamId: string;
};

export const WATCH_MULTI_MAX = 4;
export const WATCH_MULTI_STORAGE_KEY = "mlb-edge-watch-multiview";

export function toWatchBoardGames(board: GamePrediction[]): WatchBoardGame[] {
  return board.map((game) => ({
    id: game.id,
    awayTeam: normalizeTeamId(game.awayTeam),
    homeTeam: normalizeTeamId(game.homeTeam),
    startsAt: game.startsAt
  }));
}

export function watchGameLabel(game: WatchBoardGame) {
  return `${getTeam(game.awayTeam).abbreviation} @ ${getTeam(game.homeTeam).abbreviation}`;
}

export function findWatchGameForTeam(teamId: string, games: WatchBoardGame[]) {
  const id = normalizeTeamId(teamId);
  return games.find(
    (game) => normalizeTeamId(game.awayTeam) === id || normalizeTeamId(game.homeTeam) === id
  );
}

export function readWatchMultiSlots(): WatchMultiSlot[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(WATCH_MULTI_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as WatchMultiSlot[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((row) => row && typeof row.gameId === "string" && typeof row.teamId === "string")
      .slice(0, WATCH_MULTI_MAX);
  } catch {
    return [];
  }
}

export function writeWatchMultiSlots(slots: WatchMultiSlot[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(WATCH_MULTI_STORAGE_KEY, JSON.stringify(slots.slice(0, WATCH_MULTI_MAX)));
  } catch {
    // ignore quota / private mode
  }
}
