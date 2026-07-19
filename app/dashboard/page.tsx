import { GameCard } from "@/components/GameCard";
import { getTeam, predictions, teams } from "@/lib/data";

const favoriteTeamIds = ["bal", "nyy"];

export default function DashboardPage() {
  const favorites = teams.filter((team) => favoriteTeamIds.includes(team.id));
  const favoriteGames = predictions.filter((game) => favoriteTeamIds.includes(game.awayTeam) || favoriteTeamIds.includes(game.homeTeam));

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Personal board</p>
        <h1>My Teams</h1>
        <p className="lead">
          This becomes a logged-in dashboard once Supabase is connected. Favorite teams will be stored per user.
        </p>
        <div className="links">
          {favorites.map((team) => (
            <span className="badge" key={team.id}>{team.name}</span>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2>Games involving your teams</h2>
        <div className="grid">
          {favoriteGames.map((game) => (
            <GameCard game={game} key={game.id} />
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Favorite Team Settings</h2>
        <div className="grid">
          {teams.map((team) => (
            <div className="team-row" key={team.id}>
              <span className="dot" style={{ background: getTeam(team.id).primary }} />
              <span>{team.name}</span>
              {favoriteTeamIds.includes(team.id) && <span className="badge">Saved</span>}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
