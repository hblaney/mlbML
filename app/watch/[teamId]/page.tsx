import Link from "next/link";
import { notFound } from "next/navigation";
import { StreamEmbed } from "@/components/StreamEmbed";
import { GamePrediction, getTeam, teams } from "@/lib/data";
import { loadLiveGameState, LiveGameState } from "@/lib/live-game";
import { loadPredictionBoard } from "@/lib/model-output";
import { formatOdds, formatPercent } from "@/lib/odds";
import { getTeamLogoUrl } from "@/lib/team-media";
import { formatStandingRecord, loadLiveStandings, TeamStanding } from "@/lib/standings";
import { formatCentralGameTime } from "@/lib/time";
import { formatWatchGameStatusLine } from "@/lib/watch-team-status";
import { resolveBuffstreamsForGame } from "@/lib/buffstreams";
import { getTeamWatchStream } from "@/lib/watch-streams";

type WatchTeamPageProps = {
  params: Promise<{ teamId: string }>;
};

export function generateStaticParams() {
  return teams.map((team) => ({ teamId: team.id }));
}

function getFavorite(game: GamePrediction) {
  const home = getTeam(game.homeTeam);
  const away = getTeam(game.awayTeam);
  return game.modelHomeWinProbability >= game.modelAwayWinProbability ? home : away;
}

function TeamSnapshot({
  teamId,
  standing,
  label
}: {
  teamId: string;
  standing?: TeamStanding;
  label: string;
}) {
  const team = getTeam(teamId);
  const logoUrl = getTeamLogoUrl(team.id);

  return (
    <article className="panel team-snapshot-card">
      <div className="snapshot-heading">
        {logoUrl ? <img alt="" src={logoUrl} /> : null}
        <div>
          <p className="eyebrow">{label}</p>
          <h2>{team.name}</h2>
          <p className="muted">{standing?.divisionName ?? "MLB"}</p>
        </div>
      </div>
      {standing ? (
        <div className="stat-strip compact">
          <div>
            <span>Record</span>
            <strong>{formatStandingRecord(standing)}</strong>
          </div>
          <div>
            <span>Run Diff</span>
            <strong>{standing.runDifferential > 0 ? `+${standing.runDifferential}` : standing.runDifferential}</strong>
          </div>
          <div>
            <span>Last 10</span>
            <strong>{standing.last10}</strong>
          </div>
          <div>
            <span>Div Rank</span>
            <strong>{standing.divisionRank}</strong>
          </div>
        </div>
      ) : (
        <p className="muted">Live snapshot unavailable.</p>
      )}
    </article>
  );
}

function PredictionLead({
  game,
  activeTeamId,
  liveGame
}: {
  game: GamePrediction;
  activeTeamId: string;
  liveGame: LiveGameState | null;
}) {
  const away = getTeam(game.awayTeam);
  const home = getTeam(game.homeTeam);
  const favorite = getFavorite(game);
  const activeProbability =
    game.homeTeam === activeTeamId ? game.modelHomeWinProbability : game.modelAwayWinProbability;
  const pickProbability = game.pickProbability ?? Math.max(game.modelHomeWinProbability, game.modelAwayWinProbability);
  const awayLogo = getTeamLogoUrl(away.id);
  const homeLogo = getTeamLogoUrl(home.id);
  const awayPitcher = liveGame?.probablePitchers?.away ?? game.awayPitcher;
  const homePitcher = liveGame?.probablePitchers?.home ?? game.homePitcher;

  return (
    <article className="panel watch-prediction-card">
      <div className="card-ribbon" style={{ background: favorite.primary }} />
      <div className="prediction-lead-copy">
        <p className="eyebrow">Model prediction</p>
        <h2>{away.abbreviation} @ {home.abbreviation}</h2>
        <p className="muted">{formatWatchGameStatusLine(game, liveGame, activeTeamId)}</p>
      </div>

      <div className="prediction-matchup-wide">
        <div className="prediction-team">
          {awayLogo ? <img alt="" src={awayLogo} /> : null}
          <span>{away.shortName}</span>
          <strong>{formatPercent(game.modelAwayWinProbability)}</strong>
          <small>{game.awayMoneyline === null ? "No line" : formatOdds(game.awayMoneyline)}</small>
        </div>
        <div className="prediction-center">
          <span className="badge">{game.confidence}</span>
          <strong>{favorite.shortName} {formatPercent(pickProbability)}</strong>
          <span>Your team: {formatPercent(activeProbability)}</span>
        </div>
        <div className="prediction-team right">
          {homeLogo ? <img alt="" src={homeLogo} /> : null}
          <span>{home.shortName}</span>
          <strong>{formatPercent(game.modelHomeWinProbability)}</strong>
          <small>{game.homeMoneyline === null ? "No line" : formatOdds(game.homeMoneyline)}</small>
        </div>
      </div>

      <div className="bar prediction-bar" aria-label={`${home.name} win probability`}>
        <span style={{ width: `${game.modelHomeWinProbability * 100}%` }} />
      </div>

      <div className="prediction-context-grid">
        <div>
          <span>Away starter</span>
          <strong>{awayPitcher}</strong>
        </div>
        <div>
          <span>Home starter</span>
          <strong>{homePitcher}</strong>
        </div>
        <div>
          <span>Total</span>
          <strong>
            {game.projectedTotal?.toFixed(1) ?? "N/A"}
            {game.marketTotal ? ` / ${game.marketTotal.toFixed(1)} market` : ""}
          </strong>
        </div>
      </div>

    </article>
  );
}

function LiveGamePanel({ game, liveGame }: { game?: GamePrediction; liveGame: LiveGameState | null }) {
  const away = game ? getTeam(game.awayTeam) : null;
  const home = game ? getTeam(game.homeTeam) : null;

  return (
    <section className="panel live-game-panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live game tracker</p>
          <h2>Box Score & Play By Play</h2>
        </div>
        <span className="badge">{liveGame?.status ?? "Waiting for game"}</span>
      </div>

      {game && liveGame ? (
        <div className="live-game-grid">
          <div>
            <p className="muted">{liveGame.inning}</p>
            <table className="box-score-table">
              <thead>
                <tr>
                  <th>Team</th>
                  <th>R</th>
                  <th>H</th>
                  <th>E</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{away?.abbreviation}</td>
                  <td>{liveGame.away?.runs ?? 0}</td>
                  <td>{liveGame.away?.hits ?? 0}</td>
                  <td>{liveGame.away?.errors ?? 0}</td>
                </tr>
                <tr>
                  <td>{home?.abbreviation}</td>
                  <td>{liveGame.home?.runs ?? 0}</td>
                  <td>{liveGame.home?.hits ?? 0}</td>
                  <td>{liveGame.home?.errors ?? 0}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="play-feed">
            <p className="muted">Recent plays</p>
            {liveGame.recentPlays.length > 0 ? (
              liveGame.recentPlays.map((play) => <p key={play}>{play}</p>)
            ) : (
              <p>No plays posted yet. This will update when MLB live data is available.</p>
            )}
          </div>
        </div>
      ) : (
        <p className="muted">No live game feed is available for this team on today&apos;s prediction board.</p>
      )}
    </section>
  );
}

export default async function WatchTeamPage({ params }: WatchTeamPageProps) {
  const { teamId } = await params;
  const team = teams.find((item) => item.id === teamId);

  if (!team) {
    notFound();
  }

  const logoUrl = getTeamLogoUrl(team.id);
  const [predictions, standings] = await Promise.all([loadPredictionBoard(), loadLiveStandings()]);
  const standing = standings.find((item) => item.teamId === team.id);
  const teamPredictions = predictions.filter((game) => game.awayTeam === team.id || game.homeTeam === team.id);
  const primaryGame = teamPredictions[0];
  const opponentId = primaryGame?.awayTeam === team.id ? primaryGame.homeTeam : primaryGame?.awayTeam;
  const buffstreams = primaryGame ? await resolveBuffstreamsForGame(primaryGame) : null;
  const stream = getTeamWatchStream(team.id, opponentId, buffstreams);
  const opponentStanding = standings.find((item) => item.teamId === opponentId);
  const liveGame = await loadLiveGameState(primaryGame);
  const streamPageLabel = buffstreams ? "Open on Buffstreams" : "Open on MLB Webcast";

  return (
    <main className="shell stack">
      <section className="panel strong team-stream-hero">
        <div>
          <p className="eyebrow">Team stream</p>
          <h1>{team.name}</h1>
          <p className="lead">Embedded player with live game info and matchup projections.</p>
          <div className="stream-actions">
            <Link href="/watch">Back to teams</Link>
            {stream ? (
              <a href={stream.livePageUrl} rel="noopener noreferrer" target="_blank">
                {streamPageLabel}
              </a>
            ) : null}
          </div>
        </div>
        {logoUrl ? <img alt="" src={logoUrl} /> : null}
      </section>

      <section className="panel">
        {stream ? (
          <StreamEmbed sources={stream.sources} title={`${team.name} stream`} />
        ) : (
          <div className="stream-placeholder">
            {logoUrl ? <img alt="" src={logoUrl} /> : null}
            <h2>{team.abbreviation} Feed</h2>
            <p className="muted">No stream source is configured for this team.</p>
          </div>
        )}
      </section>

      {primaryGame ? (
        <PredictionLead activeTeamId={team.id} game={primaryGame} liveGame={liveGame} />
      ) : (
        <section className="panel">
          <p className="eyebrow">Model prediction</p>
          <h2>No game on today&apos;s board</h2>
          <p className="muted">No model prediction is available for {team.name} yet.</p>
        </section>
      )}

      <section className="grid two watch-insights">
        <TeamSnapshot label="Live team snapshot" standing={standing} teamId={team.id} />
        {opponentId ? (
          <TeamSnapshot label="Opponent snapshot" standing={opponentStanding} teamId={opponentId} />
        ) : (
          <article className="panel team-snapshot-card">
            <p className="eyebrow">Opponent snapshot</p>
            <h2>No opponent listed</h2>
            <p className="muted">The model board does not have a matchup for this team yet.</p>
          </article>
        )}
      </section>

      <LiveGamePanel game={primaryGame} liveGame={liveGame} />

      {teamPredictions.length > 1 ? (
        <section className="panel">
          <p className="eyebrow">Additional games</p>
          <h2>{team.shortName} has {teamPredictions.length} games on the board</h2>
          <div className="additional-game-list">
            {teamPredictions.slice(1).map((game) => (
              <p key={game.id}>
                {getTeam(game.awayTeam).abbreviation} @ {getTeam(game.homeTeam).abbreviation} ·{" "}
                {formatCentralGameTime(game.startsAt)} · {getFavorite(game).shortName}{" "}
                {formatPercent(game.pickProbability ?? Math.max(game.modelAwayWinProbability, game.modelHomeWinProbability))}
              </p>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
