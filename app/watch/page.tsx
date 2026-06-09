import { WatchTeamsGrid } from "@/components/WatchTeamsGrid";
import { getWatchTeams } from "@/lib/team-media";

export default function WatchPage() {
  const watchTeams = getWatchTeams();

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Team streams</p>
        <h1>Watch</h1>
        <p className="lead">Pick a team to open its stream page. Favorite teams appear first when you are logged in.</p>
      </section>

      <WatchTeamsGrid teams={watchTeams} />
    </main>
  );
}
