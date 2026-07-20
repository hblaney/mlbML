import {
  loadPropPredictions,
  loadPropTrackRecord,
  type PropPrediction,
} from "@/lib/model-output";

export const dynamic = "force-dynamic";

const CONF_CLASS: Record<string, string> = {
  Elite: "positive",
  High: "positive",
  Medium: "warning",
  Low: "muted",
};

function pct(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

function signedPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function americanOdds(value: number): string {
  return value > 0 ? `+${value}` : `${value}`;
}

function LegRow({ leg }: { leg: PropPrediction }) {
  return (
    <tr>
      <td>
        <strong>{leg.player}</strong>
        <div className="muted" style={{ fontSize: "0.8rem" }}>
          {leg.team ?? ""} · {leg.matchup}
        </div>
      </td>
      <td>{leg.prop_label}</td>
      <td>
        <strong>{leg.pick}</strong>
      </td>
      <td>{leg.projection}</td>
      <td>{pct(leg.model_prob)}</td>
      <td className="muted">{pct(leg.market_prob)}</td>
      <td className={leg.edge > 0 ? "positive" : "muted"}>{signedPct(leg.edge)}</td>
      <td>
        <span className={`badge ${CONF_CLASS[leg.confidence] ?? "muted"}`}>{leg.confidence}</span>
      </td>
    </tr>
  );
}

export default async function PropsPage() {
  const [data, track] = await Promise.all([loadPropPredictions(), loadPropTrackRecord()]);

  if (!data) {
    return (
      <main className="shell stack">
        <section className="panel strong">
          <p className="eyebrow">PrizePicks Props</p>
          <h1>Player Prop Predictor</h1>
          <p className="lead">No prop board yet. It builds each morning once lines post.</p>
        </section>
      </main>
    );
  }

  const parlay = data.parlay;
  const parlayProb = parlay.combined_prob ?? 0;
  const topBets = data.top_bets ?? [];

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">PrizePicks Props · {data.generated_at}</p>
        <h1>Player Prop Predictor</h1>
        <p className="lead">
          Real sportsbook prop lines (de-vigged across {`FanDuel, DraftKings, BetMGM, BetRivers, BetOnline`}) vs
          leakage-safe projections. We only lean where our model genuinely disagrees with the market.
          <strong> {data.count}</strong> actionable edges today.
        </p>
      </section>

      {topBets.length > 0 ? (
        <section className="panel strong">
          <div className="section-heading">
            <h2>Top 5 Best Bets</h2>
            <span className="badge positive">Highest confidence</span>
          </div>
          <p className="lead">
            Playable PrizePicks sides only: <strong>Less</strong> needs a standard line (demons/goblins are More-only).
            Card mixes high-confidence standard Unders with strong pitcher K Mores. Same five legs as a{" "}
            <strong>5-pick Flex</strong>.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Player</th>
                <th>Prop</th>
                <th>Pick</th>
                <th>Model</th>
                <th>Market</th>
                <th>Edge</th>
                <th>Price</th>
                <th>Conf</th>
              </tr>
            </thead>
            <tbody>
              {topBets.map((b, i) => (
                <tr key={`top-${b.player}-${b.prop}`}>
                  <td>
                    <strong>{i + 1}</strong>
                  </td>
                  <td>
                    <strong>{b.player}</strong>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      {b.team ?? ""} · {b.matchup}
                    </div>
                  </td>
                  <td>{b.prop_label}</td>
                  <td>
                    <strong>{b.side === "Over" ? "More" : "Less"} {b.line}</strong>
                    {b.pp_odds_type && b.pp_odds_type !== "standard" ? (
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        {b.pp_odds_type}
                      </div>
                    ) : (
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        standard
                      </div>
                    )}
                  </td>
                  <td>{pct(b.model_prob)}</td>
                  <td className="muted">{pct(b.market_prob)}</td>
                  <td className={b.edge > 0 ? "positive" : "muted"}>{signedPct(b.edge)}</td>
                  <td className="muted">{americanOdds(b.price)}</td>
                  <td>
                    <span className={`badge ${CONF_CLASS[b.confidence] ?? "muted"}`}>{b.confidence}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="panel strong">
        <div className="section-heading">
          <h2>Daily Prop Parlay</h2>
          <span className="badge">{parlay.n_legs}-leg {parlay.type ?? "flex"}</span>
        </div>
        {parlay.legs.length === 0 ? (
          <p className="muted">No legs available yet — check back once lines post.</p>
        ) : (
          <>
            <p className="lead">
              Same legs as Top 5 · play as <strong>Flex</strong>
              {typeof (parlay as { flex_cash_rate_oos?: number }).flex_cash_rate_oos === "number" ? (
                <>
                  {" "}
                  (OOS Flex cash rate{" "}
                  <strong>{pct((parlay as { flex_cash_rate_oos: number }).flex_cash_rate_oos)}</strong>)
                </>
              ) : null}
              . Naive all-five product: {pct(parlayProb)}.
            </p>
            <table className="table">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Prop</th>
                  <th>Pick</th>
                  <th>Proj</th>
                  <th>Model</th>
                  <th>Market</th>
                  <th>Edge</th>
                  <th>Conf</th>
                </tr>
              </thead>
              <tbody>
                {parlay.legs.map((leg) => (
                  <LegRow key={`${leg.player}-${leg.prop}`} leg={leg} />
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {track?.overall && track.overall.graded > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <h2>Track Record</h2>
          </div>
          <div className="grid two">
            <div className="metric">
              <span>Leans graded</span>
              <strong>{track.overall.graded}</strong>
            </div>
            <div className="metric">
              <span>Hit rate</span>
              <strong>{pct(track.overall.hit_rate)}</strong>
            </div>
            <div className="metric">
              <span>Record</span>
              <strong>
                {track.overall.wins}-{track.overall.losses}
                {track.overall.pushes ? ` (${track.overall.pushes}P)` : ""}
              </strong>
            </div>
            <div className="metric">
              <span>Flat ROI</span>
              <strong className={track.overall.roi >= 0 ? "positive" : "negative"}>
                {signedPct(track.overall.roi)}
              </strong>
            </div>
          </div>
          {track.parlay && track.parlay.graded > 0 ? (
            <p className="muted">
              Daily parlay: {track.parlay.wins}/{track.parlay.graded} hit ({pct(track.parlay.hit_rate)}), ROI{" "}
              {signedPct(track.parlay.roi)}
            </p>
          ) : null}
        </section>
      ) : (
        <section className="panel">
          <p className="muted">
            Track record starts building once the first day&apos;s leans are graded against real results.
          </p>
        </section>
      )}

      <section className="panel">
        <div className="section-heading compact">
          <h2>All Actionable Edges ({data.count})</h2>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Prop</th>
              <th>Pick</th>
              <th>Proj</th>
              <th>Model</th>
              <th>Market</th>
              <th>Edge</th>
              <th>Price</th>
              <th>Conf</th>
            </tr>
          </thead>
          <tbody>
            {data.predictions.map((p) => (
              <tr key={`${p.player}-${p.prop}`}>
                <td>
                  <strong>{p.player}</strong>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {p.team ?? ""} · {p.matchup}
                  </div>
                </td>
                <td>{p.prop_label}</td>
                <td>
                  <strong>{p.pick}</strong>
                </td>
                <td>{p.projection}</td>
                <td>{pct(p.model_prob)}</td>
                <td className="muted">{pct(p.market_prob)}</td>
                <td className={p.edge > 0 ? "positive" : "muted"}>{signedPct(p.edge)}</td>
                <td className="muted">{americanOdds(p.price)}</td>
                <td>
                  <span className={`badge ${CONF_CLASS[p.confidence] ?? "muted"}`}>{p.confidence}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
