import { getTeam, teamStats } from "@/lib/data";

export default function StatsPage() {
  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Model input layer</p>
        <h1>Stats</h1>
        <p className="lead">
          This page is where the full stat board lives: team quality, offense, pitching, bullpen, recent form, and
          eventually every feature used by the model.
        </p>
      </section>

      <section className="panel">
        <table className="table">
          <thead>
            <tr>
              <th>Team</th>
              <th>Record</th>
              <th>Run Diff</th>
              <th>wRC+</th>
              <th>Starter ERA</th>
              <th>Bullpen ERA</th>
              <th>Last 10</th>
              <th>Elo</th>
            </tr>
          </thead>
          <tbody>
            {teamStats.map((stat) => {
              const team = getTeam(stat.teamId);

              return (
                <tr key={stat.teamId}>
                  <td>
                    <div className="team-row">
                      <span className="dot" style={{ background: team.primary }} />
                      <strong>{team.name}</strong>
                    </div>
                  </td>
                  <td>{stat.wins}-{stat.losses}</td>
                  <td>{stat.runDifferential > 0 ? `+${stat.runDifferential}` : stat.runDifferential}</td>
                  <td>{stat.wrcPlus}</td>
                  <td>{stat.starterEra.toFixed(2)}</td>
                  <td>{stat.bullpenEra.toFixed(2)}</td>
                  <td>{stat.last10}</td>
                  <td>{stat.elo}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}
