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

function proj(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(1);
}

function isPickem(leg: PropPrediction): boolean {
  return Boolean(leg.market_is_pickem || leg.line_source === "prizepicks" || leg.market_prob == null);
}

function marketCell(leg: PropPrediction): string {
  return isPickem(leg) ? "Pick'em" : pct(leg.market_prob);
}

function pickLabel(leg: PropPrediction): string {
  if (leg.pick) return leg.pick;
  return `${leg.side === "Over" ? "More" : "Less"} ${leg.line}`;
}

function sortBoard(a: PropPrediction, b: PropPrediction): number {
  const time = (a.commence_time || "").localeCompare(b.commence_time || "");
  if (time) return time;
  const matchup = (a.matchup || "").localeCompare(b.matchup || "");
  if (matchup) return matchup;
  const player = a.player.localeCompare(b.player);
  if (player) return player;
  const prop = a.prop_label.localeCompare(b.prop_label);
  if (prop) return prop;
  return a.line - b.line || a.side.localeCompare(b.side);
}

export default async function PropsPage() {
  const [data, track] = await Promise.all([loadPropPredictions(), loadPropTrackRecord()]);

  if (!data) {
    return (
      <main className="shell stack">
        <section className="panel strong">
          <p className="eyebrow">Props</p>
          <h1>Player props</h1>
          <p className="lead">No prop board yet. It builds once lines post.</p>
        </section>
      </main>
    );
  }

  const topBets = data.top_bets ?? [];
  const parlayLegs = data.parlay?.legs ?? [];
  const cardLegs = topBets.length > 0 ? topBets : parlayLegs;
  const aceKCard = (data.ace_k_card ?? []).slice(0, 8);
  const correlatedParlays = (data.correlated_parlays ?? []).filter((c) => !c.no_bet).slice(0, 3);
  const fullBoard = [...(data.predictions ?? [])].sort(sortBoard);

  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Props · {data.generated_at}</p>
        <h1>Today&apos;s prop card</h1>
        <p className="lead">
          Play the card as a <strong>3-leg Power</strong> (or Top 5 if posted).{" "}
          <strong>Proj</strong> is the model&apos;s expected number;{" "}
          <strong>Hit %</strong> is the chance that side clears the line.
        </p>
      </section>

      <section className="panel strong">
        <div className="section-heading">
          <h2>{cardLegs.length >= 5 ? "Top card" : "Best legs"}</h2>
          <span className="badge positive">
            {cardLegs.length}-pick · Power
          </span>
        </div>
        {cardLegs.length === 0 ? (
          <p className="muted">
            {data.no_bet
              ? `No bet today${data.no_bet_reason ? ` — ${data.no_bet_reason.replaceAll("_", " ")}` : ""}.`
              : "No qualified legs yet — check back once lines firm up."}
          </p>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Player</th>
                  <th className="hide-sm">Prop</th>
                  <th>Pick</th>
                  <th>Proj</th>
                  <th>Hit %</th>
                  <th className="hide-sm">Conf</th>
                </tr>
              </thead>
              <tbody>
                {cardLegs.map((b, i) => (
                  <tr key={`card-${b.player}-${b.prop}-${b.line}`}>
                    <td>
                      <strong>{i + 1}</strong>
                    </td>
                    <td>
                      <strong>{b.player}</strong>
                      <div className="muted small">
                        {b.prop_label}
                        {b.matchup ? ` · ${b.matchup}` : ""}
                      </div>
                    </td>
                    <td className="hide-sm">{b.prop_label}</td>
                    <td>
                      <strong>{pickLabel(b)}</strong>
                    </td>
                    <td>
                      <strong>{proj(b.projection)}</strong>
                    </td>
                    <td>{pct(b.model_prob)}</td>
                    <td className="hide-sm">
                      <span className={`badge ${CONF_CLASS[b.confidence] ?? "muted"}`}>
                        {b.confidence}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {correlatedParlays.length > 0 ? (
        <section className="panel strong">
          <div className="section-heading">
            <h2>Correlated 3-legs</h2>
            <span className="badge positive">Same-game</span>
          </div>
          <p className="muted lead-tight">
            Joint probability from the PA sim — only +EV cards shown.
          </p>
          {correlatedParlays.map((card, i) => (
            <div key={`corr-${card.game_id}-${i}`} className="subcard">
              <div className="section-heading compact">
                <h3 style={{ margin: 0 }}>{card.matchup ?? card.game_id}</h3>
                <span className="badge positive">
                  EV {signedPct(card.ev_per_dollar ?? 0)} · {pct(card.joint_prob)} joint
                </span>
              </div>
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Player</th>
                      <th>Pick</th>
                      <th>Proj</th>
                      <th>Hit %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {card.legs.map((leg) => (
                      <tr key={`corr-leg-${card.game_id}-${leg.player}-${leg.prop}`}>
                        <td>
                          <strong>{leg.player}</strong>
                          <div className="muted small">{leg.prop_label}</div>
                        </td>
                        <td>
                          <strong>
                            {leg.side === "Over" ? "More" : "Less"} {leg.line}
                          </strong>
                        </td>
                        <td>
                          <strong>{proj(leg.projection)}</strong>
                        </td>
                        <td>{pct(leg.model_prob)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {aceKCard.length > 0 ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Starter K board</h2>
            <span className="badge">Top {aceKCard.length}</span>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Pitcher</th>
                  <th>Proj</th>
                  <th>Lean</th>
                  <th>Hit %</th>
                </tr>
              </thead>
              <tbody>
                {aceKCard.map((b) => (
                  <tr key={`ace-k-${b.player}-${b.line}`}>
                    <td>
                      <strong>{b.player}</strong>
                      <div className="muted small">{b.matchup}</div>
                    </td>
                    <td>
                      <strong>{proj(b.projection)}</strong>
                    </td>
                    <td>
                      <strong>More {b.line}</strong>
                    </td>
                    <td>{pct(b.model_prob)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {track?.overall && track.overall.graded > 0 ? (
        <section className="panel">
          <div className="section-heading compact">
            <h2>Track record</h2>
          </div>
          <div className="grid metrics-4">
            <div className="metric">
              <span>Graded</span>
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
              </strong>
            </div>
            <div className="metric">
              <span>ROI</span>
              <strong className={track.overall.roi >= 0 ? "positive" : "negative"}>
                {signedPct(track.overall.roi)}
              </strong>
            </div>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Full board</p>
            <h2>All props</h2>
          </div>
          <span className="muted">{fullBoard.length} lines</span>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Player</th>
                <th className="hide-sm">Matchup</th>
                <th className="hide-sm">Prop</th>
                <th>Pick</th>
                <th>Proj</th>
                <th>Hit %</th>
                <th className="hide-sm">Conf</th>
                <th className="hide-sm">Edge</th>
              </tr>
            </thead>
            <tbody>
              {fullBoard.map((p) => (
                <tr key={`${p.player}-${p.prop}-${p.line}-${p.side}-${p.pp_odds_type ?? "std"}`}>
                  <td>
                    <strong>{p.player}</strong>
                    <div className="muted small">
                      {p.prop_label}
                      {p.matchup ? ` · ${p.matchup}` : ""}
                    </div>
                  </td>
                  <td className="hide-sm muted">{p.matchup || "—"}</td>
                  <td className="hide-sm">{p.prop_label}</td>
                  <td>
                    <strong>{pickLabel(p)}</strong>
                    <div className="muted small">{marketCell(p)}</div>
                  </td>
                  <td>
                    <strong>{proj(p.projection)}</strong>
                  </td>
                  <td>{pct(p.model_prob)}</td>
                  <td className="hide-sm">
                    <span className={`badge ${CONF_CLASS[p.confidence] ?? "muted"}`}>
                      {p.confidence}
                    </span>
                  </td>
                  <td className={`hide-sm ${p.edge > 0 ? "positive" : "muted"}`}>
                    {signedPct(p.edge)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
