import { GamePrediction, getTeam } from "@/lib/data";
import { formatOdds, formatPercent } from "@/lib/odds";

export function GameCard({ game }: { game: GamePrediction }) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);
  const favorite = game.modelHomeWinProbability >= game.modelAwayWinProbability ? home : away;
  const pickProbability = game.pickProbability ?? Math.max(game.modelHomeWinProbability, game.modelAwayWinProbability);
  const awayOdds = game.awayMoneyline === null ? "Market unavailable" : formatOdds(game.awayMoneyline);
  const homeOdds = game.homeMoneyline === null ? "Market unavailable" : formatOdds(game.homeMoneyline);

  return (
    <article className="panel game-card">
      <div className="matchup">
        <div>
          <p className="muted">{new Date(game.startsAt).toLocaleString()}</p>
          <div className="team-row">
            <span className="dot" style={{ background: away.primary }} />
            {away.name}
          </div>
          <div className="team-row">
            <span className="dot" style={{ background: home.primary }} />
            {home.name}
          </div>
        </div>
        <span className="badge">{game.confidence}</span>
      </div>

      <div>
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

      <div>
        <p className="muted">Model notes</p>
        {game.explanation.map((note) => (
          <p key={note}>• {note}</p>
        ))}
      </div>
    </article>
  );
}
