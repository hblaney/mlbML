import { FavoritesClient } from "./FavoritesClient";
import { teamStats, teams } from "@/lib/data";
import { loadLiveStandings } from "@/lib/standings";

export const dynamic = "force-dynamic";

export default async function FavoritesPage() {
  const standings = await loadLiveStandings();

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Personal board</p>
        <h1>Favorites</h1>
        <p className="lead">
          Track favorite teams and players with live standings snapshots and saved player stats.
        </p>
      </section>

      <FavoritesClient standings={standings} teamStats={teamStats} teams={teams} />
    </main>
  );
}
