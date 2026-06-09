"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useFavorites } from "@/components/FavoritesProvider";
import { getTeam, type GamePrediction } from "@/lib/data";
import { formatOdds, formatPercent, impliedProbability } from "@/lib/odds";
import {
  loadPaperTrading,
  paperProfitForOdds,
  placePaperBet,
  resetPaperAccount,
  settlePaperBet,
  type PaperAccount,
  type PaperBet,
  type PaperBetInput
} from "@/lib/paper-trading";
import { formatCentralGameTime } from "@/lib/time";

type Candidate = PaperBetInput & {
  id: string;
  confidence: GamePrediction["confidence"];
  ev: number;
};

function currency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD"
  }).format(value);
}

function expectedValue(probability: number | null, odds: number, stake: number) {
  if (probability === null) {
    return 0;
  }
  const profit = paperProfitForOdds(odds, stake);
  return probability * profit - (1 - probability) * stake;
}

function buildEquityCurve(account: PaperAccount | null, settledBets: PaperBet[]) {
  const startingBalance = account?.startingBalance ?? 10000;
  let runningBalance = startingBalance;

  return [...settledBets]
    .sort((left, right) => {
      const leftTime = left.settledAt ?? left.placedAt;
      const rightTime = right.settledAt ?? right.placedAt;
      return new Date(leftTime).getTime() - new Date(rightTime).getTime();
    })
    .map((bet) => {
      runningBalance += bet.settledProfit ?? 0;
      return {
        bet,
        balance: runningBalance,
        profit: runningBalance - startingBalance,
        roi: startingBalance > 0 ? (runningBalance - startingBalance) / startingBalance : 0
      };
    });
}

function buildCandidates(board: GamePrediction[], stake: number): Candidate[] {
  return board.flatMap((game) => {
    if (game.homeMoneyline === null || game.awayMoneyline === null) {
      return [];
    }

    const away = getTeam(game.awayTeam);
    const home = getTeam(game.homeTeam);
    const matchup = `${away.abbreviation} @ ${home.abbreviation}`;
    const homeMarket = impliedProbability(game.homeMoneyline);
    const awayMarket = impliedProbability(game.awayMoneyline);
    const marketTotal = homeMarket + awayMarket;
    const homeBook = homeMarket / marketTotal;
    const awayBook = awayMarket / marketTotal;

    const rows: Candidate[] = [
      {
        id: `${game.id}-home`,
        gameId: game.id,
        startsAt: game.startsAt,
        matchup,
        teamId: home.id,
        teamName: home.name,
        opponentId: away.id,
        opponentName: away.name,
        side: "Moneyline",
        odds: game.homeMoneyline,
        stake,
        potentialProfit: paperProfitForOdds(game.homeMoneyline, stake),
        modelProbability: game.modelHomeWinProbability,
        bookProbability: homeBook,
        edge: game.modelHomeWinProbability - homeBook,
        confidence: game.confidence,
        ev: expectedValue(game.modelHomeWinProbability, game.homeMoneyline, stake)
      },
      {
        id: `${game.id}-away`,
        gameId: game.id,
        startsAt: game.startsAt,
        matchup,
        teamId: away.id,
        teamName: away.name,
        opponentId: home.id,
        opponentName: home.name,
        side: "Moneyline",
        odds: game.awayMoneyline,
        stake,
        potentialProfit: paperProfitForOdds(game.awayMoneyline, stake),
        modelProbability: game.modelAwayWinProbability,
        bookProbability: awayBook,
        edge: game.modelAwayWinProbability - awayBook,
        confidence: game.confidence,
        ev: expectedValue(game.modelAwayWinProbability, game.awayMoneyline, stake)
      }
    ];

    return rows;
  }).sort((left, right) => right.ev - left.ev);
}

export function PaperTradingClient({ board }: { board: GamePrediction[] }) {
  const { user, isReady } = useFavorites();
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [bets, setBets] = useState<PaperBet[]>([]);
  const [stake, setStake] = useState(100);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const candidates = useMemo(() => buildCandidates(board, stake), [board, stake]);
  const selected = candidates.find((candidate) => candidate.id === selectedId) ?? candidates[0] ?? null;
  const openBets = bets.filter((bet) => bet.status === "open");
  const settledBets = bets.filter((bet) => bet.status !== "open");
  const risked = openBets.reduce((total, bet) => total + bet.stake, 0);
  const settledProfit = settledBets.reduce((total, bet) => total + (bet.settledProfit ?? 0), 0);
  const settledRisk = settledBets.reduce((total, bet) => total + bet.stake, 0);
  const wins = settledBets.filter((bet) => bet.status === "won").length;
  const losses = settledBets.filter((bet) => bet.status === "lost").length;
  const gradedBets = wins + losses;
  const winRate = gradedBets > 0 ? wins / gradedBets : null;
  const paperRoi = settledRisk > 0 ? settledProfit / settledRisk : null;
  const accountReturn = account && account.startingBalance > 0 ? (account.balance - account.startingBalance) / account.startingBalance : null;
  const equityCurve = buildEquityCurve(account, settledBets);
  const recentCheckpoints = equityCurve.slice(-10).reverse();

  async function refresh() {
    if (!user) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const next = await loadPaperTrading(user.id);
      setAccount(next.account);
      setBets(next.bets);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load paper trading account.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  async function handlePlaceBet() {
    if (!user || !account || !selected) {
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      await placePaperBet(user.id, account.balance, selected);
      setMessage(`Placed ${currency(selected.stake)} on ${selected.teamName} ${formatOdds(selected.odds)}.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not place paper bet.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSettle(bet: PaperBet, status: "won" | "lost" | "void") {
    if (!user || !account) {
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      await settlePaperBet(user.id, account.balance, bet, status);
      setMessage(`Marked ${bet.teamName} as ${status}.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not settle paper bet.");
    } finally {
      setLoading(false);
    }
  }

  async function handleReset() {
    if (!user) {
      return;
    }

    const confirmed = window.confirm("Reset your paper bankroll to $10,000 and delete all paper bets?");
    if (!confirmed) {
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const nextAccount = await resetPaperAccount(user.id);
      setAccount(nextAccount);
      setBets([]);
      setMessage("Paper bankroll reset to $10,000.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reset paper trading account.");
    } finally {
      setLoading(false);
    }
  }

  if (!isReady) {
    return <section className="panel"><p className="muted">Loading account...</p></section>;
  }

  if (!user) {
    return (
      <section className="panel">
        <p className="eyebrow">Login required</p>
        <h2>Log in to paper trade</h2>
        <p className="muted">Your fake bankroll and paper bet history sync to your account.</p>
        <Link className="button" href="/login">
          Log in
        </Link>
      </section>
    );
  }

  return (
    <>
      <section className="grid">
        <article className="panel">
          <p className="muted">Paper Balance</p>
          <div className="metric">{currency(account?.balance ?? 0)}</div>
          <p className="muted">Available fake bankroll</p>
        </article>
        <article className="panel">
          <p className="muted">Open Risk</p>
          <div className="metric">{currency(risked)}</div>
          <p className="muted">{openBets.length} open tickets</p>
        </article>
        <article className="panel">
          <p className="muted">Settled P/L</p>
          <div className={settledProfit >= 0 ? "metric positive" : "metric negative"}>{currency(settledProfit)}</div>
          <p className="muted">{settledBets.length} settled tickets</p>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Performance tracker</p>
            <h2>Bankroll Over Time</h2>
          </div>
          <span>{settledBets.length} settled bets</span>
        </div>
        <div className="grid">
          <article>
            <p className="muted">Account Return</p>
            <div className={accountReturn === null || accountReturn >= 0 ? "metric positive" : "metric negative"}>
              {accountReturn === null ? "-" : formatPercent(accountReturn)}
            </div>
            <p className="muted">
              {currency(account?.startingBalance ?? 10000)} start to {currency(account?.balance ?? 0)}
            </p>
          </article>
          <article>
            <p className="muted">Paper ROI</p>
            <div className={paperRoi === null || paperRoi >= 0 ? "metric positive" : "metric negative"}>
              {paperRoi === null ? "-" : formatPercent(paperRoi)}
            </div>
            <p className="muted">{currency(settledRisk)} settled stake</p>
          </article>
          <article>
            <p className="muted">Win Rate</p>
            <div className={winRate === null || winRate >= 0.5 ? "metric positive" : "metric negative"}>
              {winRate === null ? "-" : formatPercent(winRate)}
            </div>
            <p className="muted">{wins}-{losses} graded bets</p>
          </article>
        </div>
        {recentCheckpoints.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Settled</th>
                <th>Bet</th>
                <th>Result</th>
                <th>Bet P/L</th>
                <th>Balance</th>
                <th>Return</th>
              </tr>
            </thead>
            <tbody>
              {recentCheckpoints.map((point) => (
                <tr key={point.bet.id}>
                  <td>{point.bet.settledAt ? formatCentralGameTime(point.bet.settledAt) : "-"}</td>
                  <td>
                    <strong>{point.bet.teamName}</strong>
                    <p className="muted">{point.bet.matchup}</p>
                  </td>
                  <td>{point.bet.status}</td>
                  <td className={point.bet.settledProfit !== null && point.bet.settledProfit >= 0 ? "positive" : "negative"}>
                    {currency(point.bet.settledProfit ?? 0)}
                  </td>
                  <td>{currency(point.balance)}</td>
                  <td className={point.profit >= 0 ? "positive" : "negative"}>{formatPercent(point.roi)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">Settle a paper bet to start building a bankroll curve.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Bet slip</p>
            <h2>Place a Paper Moneyline Bet</h2>
          </div>
          <button className="button secondary" disabled={loading} onClick={() => void handleReset()} type="button">
            Reset bankroll
          </button>
        </div>
        <div className="player-search-form">
          <input
            className="input"
            min="1"
            onChange={(event) => {
              const value = Number(event.target.value);
              setStake(Number.isFinite(value) ? value : 0);
            }}
            step="1"
            type="number"
            value={stake}
          />
          <button className="button" disabled={loading || !selected || stake <= 0} onClick={() => void handlePlaceBet()} type="button">
            Place Paper Bet
          </button>
        </div>
        {message ? <p className="positive">{message}</p> : null}
        {error ? <p className="negative">{error}</p> : null}
        {loading ? <p className="muted">Syncing...</p> : null}
        {selected ? (
          <p className="muted">
            Selected: <strong>{selected.teamName}</strong> {formatOdds(selected.odds)} risking {currency(selected.stake)} to win{" "}
            {currency(selected.potentialProfit)}. Model {selected.modelProbability !== null ? formatPercent(selected.modelProbability) : "-"}.
          </p>
        ) : (
          <p className="muted">No moneyline odds are available on today&apos;s board.</p>
        )}
      </section>

      <section className="panel">
        <h2>Today&apos;s Paper Board</h2>
        {candidates.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Pick</th>
                <th>Odds</th>
                <th>Model</th>
                <th>Book</th>
                <th>Edge</th>
                <th>EV / Stake</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr key={candidate.id}>
                  <td>
                    <strong>{candidate.teamName}</strong>
                    <p className="muted">
                      {candidate.matchup} · {formatCentralGameTime(candidate.startsAt)}
                    </p>
                  </td>
                  <td>{formatOdds(candidate.odds)}</td>
                  <td>{candidate.modelProbability !== null ? formatPercent(candidate.modelProbability) : "-"}</td>
                  <td>{candidate.bookProbability !== null ? formatPercent(candidate.bookProbability) : "-"}</td>
                  <td className={(candidate.edge ?? 0) >= 0 ? "positive" : "negative"}>
                    {candidate.edge !== null ? formatPercent(candidate.edge) : "-"}
                  </td>
                  <td className={candidate.ev >= 0 ? "positive" : "negative"}>{currency(candidate.ev)}</td>
                  <td>
                    <button className="button secondary" onClick={() => setSelectedId(candidate.id)} type="button">
                      Select
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No paper bet candidates are available because today&apos;s board has no moneyline odds.</p>
        )}
      </section>

      <section className="panel">
        <h2>Open Bets</h2>
        {openBets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Stake</th>
                <th>To Win</th>
                <th>Placed</th>
                <th>Settle</th>
              </tr>
            </thead>
            <tbody>
              {openBets.map((bet) => (
                <tr key={bet.id}>
                  <td>
                    <strong>{bet.teamName} {formatOdds(bet.odds)}</strong>
                    <p className="muted">{bet.matchup} · {formatCentralGameTime(bet.startsAt)}</p>
                  </td>
                  <td>{currency(bet.stake)}</td>
                  <td className="positive">{currency(bet.potentialProfit)}</td>
                  <td>{formatCentralGameTime(bet.placedAt)}</td>
                  <td>
                    <button className="button secondary" disabled={loading} onClick={() => void handleSettle(bet, "won")} type="button">
                      Win
                    </button>{" "}
                    <button className="button secondary" disabled={loading} onClick={() => void handleSettle(bet, "lost")} type="button">
                      Loss
                    </button>{" "}
                    <button className="button secondary" disabled={loading} onClick={() => void handleSettle(bet, "void")} type="button">
                      Void
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No open paper bets yet.</p>
        )}
      </section>

      <section className="panel">
        <h2>Settled History</h2>
        {settledBets.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Ticket</th>
                <th>Status</th>
                <th>Stake</th>
                <th>P/L</th>
                <th>Settled</th>
              </tr>
            </thead>
            <tbody>
              {settledBets.slice(0, 30).map((bet) => (
                <tr key={bet.id}>
                  <td>
                    <strong>{bet.teamName} {formatOdds(bet.odds)}</strong>
                    <p className="muted">{bet.matchup}</p>
                  </td>
                  <td>{bet.status}</td>
                  <td>{currency(bet.stake)}</td>
                  <td className={(bet.settledProfit ?? 0) >= 0 ? "positive" : "negative"}>
                    {currency(bet.settledProfit ?? 0)}
                  </td>
                  <td>{bet.settledAt ? formatCentralGameTime(bet.settledAt) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">Settled paper bets will show up here.</p>
        )}
      </section>
    </>
  );
}
