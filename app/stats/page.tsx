import { PlayerSearch } from "./PlayerSearch";
import { StatsClient } from "./StatsClient";
import { teamStats, teams } from "@/lib/data";
import { loadLiveStandings } from "@/lib/standings";

export const dynamic = "force-dynamic";

export default async function StatsPage() {
  const standings = await loadLiveStandings();

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Model input layer</p>
        <h1>Stats</h1>
        <p className="lead">
          Live standings, sortable team indicators, and today&apos;s probable starters.
        </p>
      </section>

      <StatsClient standings={standings} teamStats={teamStats} teams={teams} />
      <PlayerSearch />
    </main>
  );
}
