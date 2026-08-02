/**
 * Browser-side watch status from the MLB schedule API.
 * Does not depend on our /api routes (prod was 404ing /api/watch-status).
 */

import { getTeam } from "./data";
import { mlbTeamIdToLocalId } from "./standings";

type ScheduleGame = {
  gamePk?: number;
  gameDate?: string;
  status?: {
    detailedState?: string;
    abstractGameState?: string;
    codedGameState?: string;
  };
  teams?: {
    away?: { score?: number; team?: { id?: number; abbreviation?: string } };
    home?: { score?: number; team?: { id?: number; abbreviation?: string } };
  };
  linescore?: {
    currentInningOrdinal?: string;
    inningState?: string;
    teams?: {
      away?: { runs?: number };
      home?: { runs?: number };
    };
  };
};

function chicagoDateIso(d = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(d);
}

function isFinal(detailed: string, abstract?: string, coded?: string) {
  const d = detailed.toLowerCase();
  const a = (abstract ?? "").toLowerCase();
  const c = (coded ?? "").toUpperCase();
  return a === "final" || c === "F" || d.includes("final") || d.includes("game over") || d.includes("completed");
}

function isLive(detailed: string, abstract?: string) {
  if (isFinal(detailed, abstract)) return false;
  const d = detailed.toLowerCase();
  const a = (abstract ?? "").toLowerCase();
  return a === "live" || d.includes("progress") || d.includes("live") || d.includes("manager challenge");
}

function inningLabel(game: ScheduleGame) {
  const detailed = game.status?.detailedState ?? "";
  if (isFinal(detailed, game.status?.abstractGameState, game.status?.codedGameState)) {
    return "Final";
  }
  const ordinal = game.linescore?.currentInningOrdinal;
  const state = game.linescore?.inningState;
  if (!ordinal) return "Pregame";
  if (state?.toLowerCase() === "top") return `↑ ${ordinal}`;
  if (state?.toLowerCase() === "bottom") return `↓ ${ordinal}`;
  return [state, ordinal].filter(Boolean).join(" ");
}

function teamAbbr(mlbId: number | undefined, fallback: string) {
  if (mlbId == null) return fallback;
  const localId = mlbTeamIdToLocalId[mlbId];
  if (!localId) return fallback;
  try {
    return getTeam(localId).abbreviation;
  } catch {
    return fallback;
  }
}

function scoreLine(game: ScheduleGame, prefix: string) {
  const awayAbbr = teamAbbr(game.teams?.away?.team?.id, game.teams?.away?.team?.abbreviation ?? "AWAY");
  const homeAbbr = teamAbbr(game.teams?.home?.team?.id, game.teams?.home?.team?.abbreviation ?? "HOME");
  const awayRuns = game.linescore?.teams?.away?.runs ?? game.teams?.away?.score ?? 0;
  const homeRuns = game.linescore?.teams?.home?.runs ?? game.teams?.home?.score ?? 0;
  return `${prefix} · ${awayAbbr} ${awayRuns}-${homeRuns} ${homeAbbr}`;
}

function scheduleLine(game: ScheduleGame) {
  const when = game.gameDate
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short"
      }).format(new Date(game.gameDate))
    : "Scheduled";
  const away = teamAbbr(game.teams?.away?.team?.id, "AWAY");
  const home = teamAbbr(game.teams?.home?.team?.id, "HOME");
  return `${when.replace(",", "")} · ${away}@${home}`;
}

function statusForGame(game: ScheduleGame) {
  const detailed = game.status?.detailedState ?? "";
  const abstract = game.status?.abstractGameState;
  if (isFinal(detailed, abstract, game.status?.codedGameState)) {
    return scoreLine(game, "Final");
  }
  if (isLive(detailed, abstract)) {
    return scoreLine(game, inningLabel(game));
  }
  return scheduleLine(game);
}

function statusRank(line: string) {
  if (line.includes("↑") || line.includes("↓")) return 3;
  if (line.startsWith("Final")) return 2;
  return 1;
}

async function fetchDay(day: string): Promise<ScheduleGame[]> {
  const url = `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=${day}&hydrate=linescore`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) return [];
  const payload = (await response.json()) as { dates?: { games?: ScheduleGame[] }[] };
  return (payload.dates ?? []).flatMap((d) => d.games ?? []);
}

/** Map local team id → status line from today's (+ yesterday's) MLB slate. */
export async function fetchClientWatchStatusLines(): Promise<Record<string, string>> {
  const today = chicagoDateIso();
  const yesterday = chicagoDateIso(new Date(Date.now() - 86_400_000));
  const games = [...(await fetchDay(today)), ...(await fetchDay(yesterday))];

  const best: Record<string, string> = {};
  const bestRank: Record<string, number> = {};

  for (const game of games) {
    const line = statusForGame(game);
    const r = statusRank(line);
    for (const side of ["away", "home"] as const) {
      const mlbId = game.teams?.[side]?.team?.id;
      if (mlbId == null) continue;
      const localId = mlbTeamIdToLocalId[mlbId];
      if (!localId) continue;
      if ((bestRank[localId] ?? 0) < r) {
        best[localId] = line;
        bestRank[localId] = r;
      }
    }
  }

  return best;
}
