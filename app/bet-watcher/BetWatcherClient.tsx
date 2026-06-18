"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { StreamEmbed } from "@/components/StreamEmbed";
import type { GamePrediction } from "@/lib/data";
import { getTeam } from "@/lib/data";
import {
  BetLeg,
  combinedAmericanOdds,
  createLegId,
  evaluateParlay,
  formatLegSummary,
  LegKind,
  profitFromAmericanOdds,
  uniqueGameIds
} from "@/lib/bet-watcher";
import type { LiveGameState } from "@/lib/live-game";
import { formatOdds } from "@/lib/odds";
import type { WatchStreamSource } from "@/lib/watch-streams";
import { getTeamLogoUrl } from "@/lib/team-media";
import { formatCentralGameTime } from "@/lib/time";

type TodayTicketSeed = {
  legs: BetLeg[];
  stake: number;
  americanOdds: number | null;
  label: string;
};

type BetWatcherClientProps = {
  board: GamePrediction[];
  todayTicket: TodayTicketSeed | null;
};

type StreamBundle = WatchStreamSource & {
  gameId: string;
  title: string;
  teamId: string;
};

const STORAGE_KEY = "mlb-edge-bet-watcher";

type SavedWatcherState = {
  legs: BetLeg[];
  stake: number;
  manualOdds: number | null;
};

function defaultLeg(board: GamePrediction[]): BetLeg {
  const game = board[0];
  return {
    id: createLegId(),
    gameId: game?.id ?? "",
    kind: "moneyline",
    teamId: game?.homeTeam,
    odds: game?.homeMoneyline ?? undefined
  };
}

function readSavedState(): SavedWatcherState | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }

    return JSON.parse(raw) as SavedWatcherState;
  } catch {
    return null;
  }
}

function statusClass(status: string) {
  if (status === "won" || status === "winning") {
    return "leg-status good";
  }

  if (status === "lost" || status === "losing" || status === "dead") {
    return "leg-status bad";
  }

  if (status === "alive") {
    return "leg-status live";
  }

  return "leg-status";
}

export function BetWatcherClient({ board, todayTicket }: BetWatcherClientProps) {
  const gamesById = useMemo(() => new Map(board.map((game) => [game.id, game])), [board]);
  const [legs, setLegs] = useState<BetLeg[]>(() => [defaultLeg(board)]);
  const [stake, setStake] = useState(todayTicket?.stake ?? 5);
  const [manualOdds, setManualOdds] = useState<number | null>(todayTicket?.americanOdds ?? null);
  const [liveByGameId, setLiveByGameId] = useState<Map<string, LiveGameState | null>>(new Map());
  const [streamsByGameId, setStreamsByGameId] = useState<Map<string, StreamBundle>>(new Map());
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const saved = readSavedState();
    if (saved?.legs?.length) {
      setLegs(saved.legs);
      setStake(saved.stake);
      setManualOdds(saved.manualOdds);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) {
      return;
    }

    const payload: SavedWatcherState = { legs, stake, manualOdds };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }, [hydrated, legs, manualOdds, stake]);

  const autoOdds = useMemo(() => combinedAmericanOdds(legs), [legs]);
  const activeOdds = manualOdds ?? autoOdds;
  const evaluation = useMemo(
    () => evaluateParlay(legs, gamesById, liveByGameId),
    [gamesById, legs, liveByGameId]
  );

  const potentialProfit = activeOdds == null ? null : profitFromAmericanOdds(stake, activeOdds);
  const potentialPayout = potentialProfit == null ? null : stake + potentialProfit;
  const currentPayout =
    evaluation.status === "won" && activeOdds != null
      ? stake + profitFromAmericanOdds(stake, activeOdds)
      : evaluation.status === "dead"
        ? 0
        : null;

  const refreshLive = useCallback(async () => {
    const gameIds = uniqueGameIds(legs);
    if (gameIds.length === 0) {
      return;
    }

    const response = await fetch("/api/bet-watcher/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gameIds })
    });

    if (!response.ok) {
      return;
    }

    const payload = (await response.json()) as {
      games: Record<string, LiveGameState | null>;
      refreshedAt?: string;
    };

    setLiveByGameId(new Map(Object.entries(payload.games)));
    setLastRefresh(payload.refreshedAt ?? new Date().toISOString());
  }, [legs]);

  useEffect(() => {
    void refreshLive();
    const timer = window.setInterval(() => {
      void refreshLive();
    }, 20_000);

    return () => window.clearInterval(timer);
  }, [refreshLive]);

  useEffect(() => {
    const gameIds = uniqueGameIds(legs);

    for (const gameId of gameIds) {
      if (streamsByGameId.has(gameId)) {
        continue;
      }

      const leg = legs.find((item) => item.gameId === gameId);
      const focusTeamId = leg?.teamId ?? gamesById.get(gameId)?.homeTeam;
      const query = new URLSearchParams({ gameId });
      if (focusTeamId) {
        query.set("teamId", focusTeamId);
      }

      void fetch(`/api/bet-watcher/stream?${query.toString()}`)
        .then((response) => (response.ok ? response.json() : null))
        .then((payload: StreamBundle | null) => {
          if (!payload) {
            return;
          }

          setStreamsByGameId((current) => {
            if (current.has(gameId)) {
              return current;
            }

            const next = new Map(current);
            next.set(gameId, payload);
            return next;
          });
        });
    }
  }, [gamesById, legs, streamsByGameId]);

  function updateLeg(legId: string, patch: Partial<BetLeg>) {
    setLegs((current) => current.map((leg) => (leg.id === legId ? { ...leg, ...patch } : leg)));
  }

  function addLeg() {
    setLegs((current) => [...current, defaultLeg(board)]);
  }

  function removeLeg(legId: string) {
    setLegs((current) => (current.length <= 1 ? current : current.filter((leg) => leg.id !== legId)));
  }

  function loadTodayCard() {
    if (!todayTicket?.legs.length) {
      return;
    }

    setLegs(todayTicket.legs.map((leg) => ({ ...leg, id: createLegId() })));
    setStake(todayTicket.stake);
    setManualOdds(todayTicket.americanOdds);
    setStreamsByGameId(new Map());
  }

  const streamPanels = uniqueGameIds(legs)
    .map((gameId) => streamsByGameId.get(gameId))
    .filter((item): item is StreamBundle => Boolean(item));

  return (
    <div className="stack bet-watcher">
      <section className="panel strong bet-watcher-summary">
        <div className="bet-watcher-summary-copy">
          <p className="eyebrow">Live ticket tracker</p>
          <h2 className={statusClass(evaluation.status)}>{evaluation.headline}</h2>
          <p className="muted">
            {evaluation.wonLegs}/{evaluation.totalLegs} legs cleared
            {lastRefresh ? ` · updated ${new Date(lastRefresh).toLocaleTimeString()}` : ""}
          </p>
        </div>
        <div className="bet-watcher-payout-grid">
          <div>
            <span>Stake</span>
            <strong>${stake.toFixed(2)}</strong>
          </div>
          <div>
            <span>Ticket odds</span>
            <strong>{activeOdds == null ? "—" : formatOdds(activeOdds)}</strong>
          </div>
          <div>
            <span>If it hits</span>
            <strong>{potentialPayout == null ? "—" : `$${potentialPayout.toFixed(2)}`}</strong>
          </div>
          <div>
            <span>Current value</span>
            <strong>
              {currentPayout == null
                ? evaluation.status === "alive"
                  ? "Still live"
                  : "—"
                : `$${currentPayout.toFixed(2)}`}
            </strong>
          </div>
        </div>
      </section>

      <section className="panel bet-watcher-builder">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Build your bet</p>
            <h2>Legs</h2>
          </div>
          <div className="bet-watcher-actions">
            {todayTicket?.legs.length ? (
              <button className="button" onClick={loadTodayCard} type="button">
                Load {todayTicket.label}
              </button>
            ) : null}
            <button className="button" onClick={addLeg} type="button">
              Add leg
            </button>
            <button className="button" onClick={() => void refreshLive()} type="button">
              Refresh scores
            </button>
          </div>
        </div>

        <div className="bet-watcher-controls">
          <label>
            <span>Stake ($)</span>
            <input
              min={0}
              onChange={(event) => setStake(Number(event.target.value) || 0)}
              step={0.5}
              type="number"
              value={stake}
            />
          </label>
          <label>
            <span>Combined odds (American)</span>
            <input
              onChange={(event) => {
                const value = event.target.value.trim();
                setManualOdds(value === "" ? null : Number(value));
              }}
              placeholder={autoOdds == null ? "Auto from legs" : `${autoOdds}`}
              type="number"
              value={manualOdds ?? ""}
            />
          </label>
          {autoOdds != null && manualOdds == null ? (
            <p className="muted bet-watcher-auto-odds">Auto-combined from leg odds: {formatOdds(autoOdds)}</p>
          ) : null}
        </div>

        <div className="bet-watcher-leg-list">
          {legs.map((leg, index) => {
            const game = gamesById.get(leg.gameId);
            const legEval = evaluation.legs.find((item) => item.legId === leg.id);
            const live = liveByGameId.get(leg.gameId) ?? null;

            return (
              <article className="bet-watcher-leg" key={leg.id}>
                <div className="bet-watcher-leg-head">
                  <div>
                    <p className="eyebrow">Leg {index + 1}</p>
                    <h3>{game ? formatLegSummary(leg, game) : "Select a game"}</h3>
                    {legEval ? <p className={statusClass(legEval.status)}>{legEval.detail}</p> : null}
                    {legEval ? <p className="muted">{legEval.scoreLine}</p> : null}
                    {live ? <p className="muted">{live.inning} · {live.status}</p> : null}
                  </div>
                  <button className="text-button" onClick={() => removeLeg(leg.id)} type="button">
                    Remove
                  </button>
                </div>

                <div className="bet-watcher-leg-fields">
                  <label>
                    <span>Game</span>
                    <select
                      onChange={(event) => {
                        const nextGame = gamesById.get(event.target.value);
                        updateLeg(leg.id, {
                          gameId: event.target.value,
                          teamId: nextGame?.homeTeam,
                          line: nextGame?.marketTotal ?? leg.line,
                          odds: nextGame?.homeMoneyline ?? undefined
                        });
                      }}
                      value={leg.gameId}
                    >
                      {board.map((item) => (
                        <option key={item.id} value={item.id}>
                          {getTeam(item.awayTeam).abbreviation} @ {getTeam(item.homeTeam).abbreviation} ·{" "}
                          {formatCentralGameTime(item.startsAt)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    <span>Market</span>
                    <select
                      onChange={(event) => {
                        const kind = event.target.value as LegKind;
                        const patch: Partial<BetLeg> = { kind };
                        if (kind === "moneyline" && game) {
                          patch.teamId = game.homeTeam;
                          patch.odds = game.homeMoneyline ?? undefined;
                        }
                        if ((kind === "over" || kind === "under") && game) {
                          patch.line = game.marketTotal ?? game.projectedTotal ?? undefined;
                          patch.odds = kind === "over" ? (game.overPrice ?? undefined) : (game.underPrice ?? undefined);
                        }
                        updateLeg(leg.id, patch);
                      }}
                      value={leg.kind}
                    >
                      <option value="moneyline">Moneyline</option>
                      <option value="over">Total over</option>
                      <option value="under">Total under</option>
                    </select>
                  </label>

                  {leg.kind === "moneyline" ? (
                    <label>
                      <span>Team</span>
                      <select
                        onChange={(event) => {
                          const teamId = event.target.value;
                          const odds =
                            game && teamId === game.homeTeam
                              ? game.homeMoneyline
                              : game?.awayMoneyline;
                          updateLeg(leg.id, { teamId, odds: odds ?? undefined });
                        }}
                        value={leg.teamId ?? ""}
                      >
                        {game ? (
                          <>
                            <option value={game.awayTeam}>{getTeam(game.awayTeam).name}</option>
                            <option value={game.homeTeam}>{getTeam(game.homeTeam).name}</option>
                          </>
                        ) : null}
                      </select>
                    </label>
                  ) : (
                    <label>
                      <span>Line</span>
                      <input
                        onChange={(event) => updateLeg(leg.id, { line: Number(event.target.value) || undefined })}
                        step={0.5}
                        type="number"
                        value={leg.line ?? ""}
                      />
                    </label>
                  )}

                  <label>
                    <span>Leg odds</span>
                    <input
                      onChange={(event) => updateLeg(leg.id, { odds: Number(event.target.value) || undefined })}
                      type="number"
                      value={leg.odds ?? ""}
                    />
                  </label>
                </div>

                {leg.teamId ? (
                  <Link className="team-stream-link" href={`/watch/${leg.teamId}`}>
                    Open full {getTeam(leg.teamId).abbreviation} watch page
                  </Link>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Multi-view</p>
            <h2>Game streams</h2>
          </div>
          <p className="muted">One embed per unique game on your ticket. Same feeds as the team watch pages.</p>
        </div>

        {streamPanels.length > 0 ? (
          <div className="bet-watcher-stream-grid">
            {streamPanels.map((stream) => {
              const game = gamesById.get(stream.gameId);
              const awayLogo = game ? getTeamLogoUrl(game.awayTeam) : null;
              const homeLogo = game ? getTeamLogoUrl(game.homeTeam) : null;

              return (
                <article className="bet-watcher-stream-card" key={stream.gameId}>
                  <div className="bet-watcher-stream-head">
                    <div className="bet-watcher-stream-logos">
                      {awayLogo ? <img alt="" src={awayLogo} /> : null}
                      {homeLogo ? <img alt="" src={homeLogo} /> : null}
                    </div>
                    <div>
                      <h3>{stream.title}</h3>
                      <Link href={`/watch/${stream.teamId}`}>Full watch page ↗</Link>
                    </div>
                  </div>
                  <StreamEmbed sources={stream.sources} title={stream.title} />
                </article>
              );
            })}
          </div>
        ) : (
          <p className="muted">Add legs to load streams for each game.</p>
        )}
      </section>
    </div>
  );
}
