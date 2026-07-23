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

function americanOdds(value: number | null | undefined): string {
  if (value === undefined || value === null) return "—";
  return value > 0 ? `+${value}` : `${value}`;
}

function isPickem(leg: PropPrediction): boolean {
  return Boolean(leg.market_is_pickem || leg.line_source === "prizepicks" || leg.market_prob == null);
}

function marketCell(leg: PropPrediction): string {
  return isPickem(leg) ? "Pick'em" : pct(leg.market_prob);
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
      <td className="muted">{marketCell(leg)}</td>
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
  const aceKCard = data.ace_k_card ?? [];
  const correlatedParlays = data.correlated_parlays ?? [];

  // Best-to-bet-first: playable PrizePicks sides, highest model hit % first.
  // Demon/goblin Unders and coin-flip junk sink to the bottom (or drop out).
  const confRank: Record<string, number> = { Elite: 0, High: 1, Medium: 2, Low: 3 };
  const actionableEdges = [...(data.predictions ?? [])]
    .filter((p) => {
      const odds = (p.pp_odds_type || "standard").toLowerCase();
      if ((odds === "demon" || odds === "goblin") && p.side === "Under") return false;
      if (p.coin_flip) return false;
      return true;
    })
    .sort((a, b) => {
      const baby = (p: PropPrediction) =>
        p.prop === "pitcher_strikeouts" && p.side === "Over" && p.line < 5.5 ? 1 : 0;
      if (baby(a) !== baby(b)) return baby(a) - baby(b);
      const ca = confRank[a.confidence] ?? 4;
      const cb = confRank[b.confidence] ?? 4;
      if (ca !== cb) return ca - cb;
      if (b.model_prob !== a.model_prob) return b.model_prob - a.model_prob;
      return b.edge - a.edge;
    });

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">PrizePicks Props · {data.generated_at}</p>
        <h1>Player Prop Predictor</h1>
        <p className="lead">
          {data.line_source === "prizepicks" || data.predictions.some((p) => p.line_source === "prizepicks") ? (
            <>
              Live <strong>PrizePicks</strong> lines (pick&apos;em — no sportsbook juice). Model % is hit
              probability; edge is vs a 50/50 prior, not FanDuel/DK odds.
            </>
          ) : (
            <>
              De-vigged sportsbook prop lines vs leakage-safe projections. We only lean where the model
              disagrees with the books.
            </>
          )}{" "}
          <strong>{actionableEdges.length}</strong> actionable edges today, ranked best-to-bet.
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
                <th>vs Pick&apos;em</th>
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
                  <td className="muted">{marketCell(b)}</td>
                  <td className={b.edge > 0 ? "positive" : "muted"}>{signedPct(b.edge)}</td>
                  <td>
                    <span className={`badge ${CONF_CLASS[b.confidence] ?? "muted"}`}>{b.confidence}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {aceKCard.length > 0 ? (
        <section className="panel strong">
          <div className="section-heading">
            <h2>Starter K Board</h2>
            <span className="badge">Every slate arm</span>
          </div>
          <p className="lead">
            Projected strikeouts for today&apos;s starters — including aces PrizePicks never posted.
            Bet the line when PP/books offer it; <strong>proj</strong> is the model&apos;s expected Ks.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Pitcher</th>
                <th>Proj K</th>
                <th>Lean</th>
                <th>Model</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {aceKCard.map((b) => (
                <tr key={`ace-k-${b.player}-${b.line}`}>
                  <td>
                    <strong>{b.player}</strong>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      {b.matchup}
                    </div>
                  </td>
                  <td>
                    <strong>{b.projection}</strong>
                  </td>
                  <td>
                    <strong>
                      More {b.line}
                    </strong>
                  </td>
                  <td>{pct(b.model_prob)}</td>
                  <td className="muted">
                    {b.line_source === "model_slate" ? "model (no PP line)" : b.line_source ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {correlatedParlays.length > 0 ? (
        <section className="panel strong">
          <div className="section-heading">
            <h2>Correlated 3-Leg Parlays</h2>
            <span className="badge positive">Same-game · sim joint</span>
          </div>
          <p className="lead">
            Same-game 3-leg cards priced by the <strong>PA Monte Carlo joint probability</strong> — not the
            product of independent legs. <strong>Lift</strong> above 1.00 means the legs tend to win in the
            same simulated game (the only real edge a parlay has). <strong>Joint %</strong> is the
            correlation-aware hit rate; EV is per $1 on a PrizePicks 3-pick Power.
          </p>
          {correlatedParlays.map((card, i) => (
            <div key={`corr-${card.game_id}-${i}`} style={{ marginBottom: "1.25rem" }}>
              <div className="section-heading compact">
                <h3 style={{ margin: 0 }}>
                  {card.matchup ?? card.game_id}
                </h3>
                <span className={`badge ${card.no_bet ? "muted" : "positive"}`}>
                  {card.no_bet ? "No bet (−EV)" : `EV ${signedPct(card.ev_per_dollar ?? 0)}`}
                </span>
              </div>
              <p className="muted" style={{ marginTop: "0.25rem" }}>
                Joint <strong>{pct(card.joint_prob)}</strong>
                {" · "}independent {pct(card.independent_prob ?? 0)}
                {" · "}lift{" "}
                <strong className={(card.correlation_lift ?? 1) >= 1 ? "positive" : "negative"}>
                  {(card.correlation_lift ?? 1).toFixed(2)}×
                </strong>
                {typeof card.payout === "number" ? ` · pays ${card.payout}×` : ""}
              </p>
              <table className="table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Prop</th>
                    <th>Pick</th>
                    <th>Proj</th>
                    <th>Model</th>
                  </tr>
                </thead>
                <tbody>
                  {card.legs.map((leg) => (
                    <tr key={`corr-leg-${card.game_id}-${leg.player}-${leg.prop}`}>
                      <td>
                        <strong>{leg.player}</strong>
                        <div className="muted" style={{ fontSize: "0.8rem" }}>
                          {leg.team ?? ""}
                        </div>
                      </td>
                      <td>{leg.prop_label}</td>
                      <td>
                        <strong>
                          {leg.side === "Over" ? "More" : "Less"} {leg.line}
                        </strong>
                      </td>
                      <td>{leg.projection}</td>
                      <td>{pct(leg.model_prob)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
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
                  <th>vs Pick&apos;em</th>
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
          <h2>All Actionable Edges ({actionableEdges.length})</h2>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Sorted by confidence, then model hit probability. Unplayable demon/goblin Unders excluded.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>Player</th>
              <th>Prop</th>
              <th>Pick</th>
              <th>Proj</th>
              <th>Model</th>
              <th>Market</th>
              <th>vs Pick&apos;em</th>
              <th>Conf</th>
            </tr>
          </thead>
          <tbody>
            {actionableEdges.map((p, i) => (
              <tr key={`${p.player}-${p.prop}-${p.line}-${p.side}`}>
                <td className="muted">{i + 1}</td>
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
                <td className="muted">{marketCell(p)}</td>
                <td className={p.edge > 0 ? "positive" : "muted"}>{signedPct(p.edge)}</td>
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
