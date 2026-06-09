import { FavoriteButton } from "@/components/FavoriteButton";
import { GamePrediction, getTeam } from "@/lib/data";
import { formatOdds, formatPercent } from "@/lib/odds";

export function GameCard({ game, recordsByTeamId = {} }: { game: GamePrediction; recordsByTeamId?: Record<string, string> }) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);
  const awayRecord = recordsByTeamId[game.awayTeam];
  const homeRecord = recordsByTeamId[game.homeTeam];
  const favorite = game.modelHomeWinProbability >= game.modelAwayWinProbability ? home : away;
  const pickProbability = game.pickProbability ?? Math.max(game.modelHomeWinProbability, game.modelAwayWinProbability);
  const awayOdds = game.awayMoneyline === null ? "Market unavailable" : formatOdds(game.awayMoneyline);
  const homeOdds = game.homeMoneyline === null ? "Market unavailable" : formatOdds(game.homeMoneyline);
  const matchup = `${away.abbreviation} @ ${home.abbreviation}`;

  return (
    <article className="panel game-card">
      <div className="card-ribbon" style={{ background: favorite.primary }} />
      <div className="matchup">
        <div>
          <p className="card-kicker">{matchup}</p>
          <p className="muted">{new Date(game.startsAt).toLocaleString()}</p>
          <div className="team-row">
            <FavoriteButton kind="team" label={away.name} teamId={away.id} />
            <span className="dot" style={{ background: away.primary }} />
            <span>{away.abbreviation}</span>
            <span className="team-name">{away.shortName}</span>
            {awayRecord ? <span className="team-record">{awayRecord}</span> : null}
          </div>
          <div className="team-row">
            <FavoriteButton kind="team" label={home.name} teamId={home.id} />
            <span className="dot" style={{ background: home.primary }} />
            <span>{home.abbreviation}</span>
            <span className="team-name">{home.shortName}</span>
            {homeRecord ? <span className="team-record">{homeRecord}</span> : null}
          </div>
        </div>
        <span className="badge">{game.confidence}</span>
      </div>

      <div className="pick-block">
        <p className="muted">Prediction probability</p>
        <div className="metric">{favorite.shortName} {formatPercent(pickProbability)}</div>
        <p className="muted">Confidence: {game.confidence}</p>
      </div>

      <div className="bar" aria-label={`${home.name} win probability`}>
        <span style={{ width: `${game.modelHomeWinProbability * 100}%` }} />
      </div>

      <div className="grid two">
        <div>
          <p className="muted">Away starter</p>
          <strong>{game.awayPitcher}</strong>
          <p className="muted">{formatPercent(game.modelAwayWinProbability)} · {awayOdds}</p>
        </div>
        <div>
          <p className="muted">Home starter</p>
          <strong>{game.homePitcher}</strong>
          <p className="muted">{formatPercent(game.modelHomeWinProbability)} · {homeOdds}</p>
        </div>
      </div>
    </article>
  );
}
