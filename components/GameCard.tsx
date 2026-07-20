import Link from "next/link";
import { FavoriteButton } from "@/components/FavoriteButton";
import { GamePrediction, getTeam } from "@/lib/data";
import { formatOdds, formatPercent, impliedProbability } from "@/lib/odds";
import { formatCentralGameTime } from "@/lib/time";

function noVigImplied(homeMl: number | null, awayMl: number | null): { home: number; away: number } | null {
  if (homeMl == null || awayMl == null) return null;
  const h = impliedProbability(homeMl);
  const a = impliedProbability(awayMl);
  const t = h + a;
  if (t <= 0) return null;
  return { home: h / t, away: a / t };
}

export function GameCard({ game, recordsByTeamId = {} }: { game: GamePrediction; recordsByTeamId?: Record<string, string> }) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);
  const awayRecord = recordsByTeamId[game.awayTeam];
  const homeRecord = recordsByTeamId[game.homeTeam];
  const favorite = game.modelHomeWinProbability >= game.modelAwayWinProbability ? home : away;
  const pickProbability = game.pickProbability ?? Math.max(game.modelHomeWinProbability, game.modelAwayWinProbability);
  const awayOdds = game.awayMoneyline === null ? "—" : formatOdds(game.awayMoneyline);
  const homeOdds = game.homeMoneyline === null ? "—" : formatOdds(game.homeMoneyline);
  const market = noVigImplied(game.homeMoneyline, game.awayMoneyline);
  const pickIsHome = game.modelHomeWinProbability >= game.modelAwayWinProbability;
  const marketForPick = market ? (pickIsHome ? market.home : market.away) : null;
  const edge = game.modelEdge ?? (marketForPick != null ? pickProbability - marketForPick : null);
  const matchup = `${away.abbreviation} @ ${home.abbreviation}`;

  return (
    <article className="panel game-card">
      <div className="card-ribbon" style={{ background: favorite.primary }} />
      <div className="matchup">
        <div>
          <p className="card-kicker">{matchup}</p>
          <p className="muted">{formatCentralGameTime(game.startsAt)}</p>
          <div className="team-row">
            <FavoriteButton kind="team" label={away.name} teamId={away.id} />
            <span className="dot" style={{ background: away.primary }} />
            <span className="team-abbrev">{away.abbreviation}</span>
            <Link className="team-name team-stream-link" href={`/watch/${away.id}`} title={`Open ${away.name} stream page`}>
              {away.shortName}
            </Link>
            {awayRecord ? <span className="team-record">{awayRecord}</span> : null}
          </div>
          <div className="team-row">
            <FavoriteButton kind="team" label={home.name} teamId={home.id} />
            <span className="dot" style={{ background: home.primary }} />
            <span className="team-abbrev">{home.abbreviation}</span>
            <Link className="team-name team-stream-link" href={`/watch/${home.id}`} title={`Open ${home.name} stream page`}>
              {home.shortName}
            </Link>
            {homeRecord ? <span className="team-record">{homeRecord}</span> : null}
          </div>
        </div>
        <span className="badge">{game.confidence}</span>
      </div>

      <div className="pick-block">
        <p className="muted">Sim win probability</p>
        <div className="metric">{favorite.shortName} {formatPercent(pickProbability)}</div>
        <p className="muted">
          {marketForPick != null ? (
            <>
              Market {formatPercent(marketForPick)}
              {edge != null ? (
                <>
                  {" "}
                  · Edge{" "}
                  <span className={edge >= 0 ? "positive" : "negative"}>
                    {edge >= 0 ? "+" : ""}
                    {formatPercent(edge)}
                  </span>
                </>
              ) : null}
            </>
          ) : (
            <>Confidence: {game.confidence}</>
          )}
        </p>
      </div>

      <div className="bar" aria-label={`${home.name} win probability`}>
        <span style={{ width: `${game.modelHomeWinProbability * 100}%` }} />
      </div>

      <div className="grid two">
        <div>
          <p className="muted">Away starter</p>
          <strong>{game.awayPitcher}</strong>
          <p className="muted">
            Sim {formatPercent(game.modelAwayWinProbability)}
            {market ? ` · Mkt ${formatPercent(market.away)}` : ""} · {awayOdds}
          </p>
        </div>
        <div>
          <p className="muted">Home starter</p>
          <strong>{game.homePitcher}</strong>
          <p className="muted">
            Sim {formatPercent(game.modelHomeWinProbability)}
            {market ? ` · Mkt ${formatPercent(market.home)}` : ""} · {homeOdds}
          </p>
        </div>
      </div>
    </article>
  );
}
