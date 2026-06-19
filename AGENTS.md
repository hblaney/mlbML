# MLB Edge — autonomous agent ops

You own this system. Treat the user's wallet (~$23) as real money. Do not wait to be asked.

## Every session (do first, no prompt needed)

1. **Read state**: `public/live-bankroll.json`, `public/predictions.json`, `public/betting-plan.json`
2. **Grade & refresh**: `python3 scripts/model/update_live_bankroll.py --wallet <current_wallet>`
3. **Report today's system ticket**: `trg59_top_prob_2`, model-pick-only, stakes 35/45/10
4. **Flag**: stale board (>2h), TBD/changed starters, missing odds, site vs local drift
5. **Fix blockers** before new features (broken deploy, wrong ticket logic, SSL/odds)

## Daily schedule (GitHub Actions — verify they ran)

| Time (CT) | Workflow | Purpose |
|-----------|----------|---------|
| ~5 AM | `daily-model.yml` | Retrain, full `model:daily`, commit outputs |
| Hourly 10 AM–10 PM CT | `refresh-board.yml` | Starters/odds refresh → commit → Vercel redeploy |
| After daily model | `refresh-board.yml` | Same refresh when morning retrain finishes |

**Refreshing Chrome does not fetch MLB live.** Updates only appear after GitHub Actions commits `predictions.json` and Vercel redeploys (~2 min).

## Betting rules (canonical — never drift)

- **Strategy**: `trg59_top_prob_2` (legacy: `med60_force2_223s`, `no_low_parlay_223s`)
- **Sides**: model predicted winner only (never +EV fade)
- **Stakes**: 35% single · 45% two-leg · 10% three-leg of **wallet_balance**
- **One ticket per day** — user does not add picks

## Model improvement loop (ongoing)

Priority order:

1. **Live accuracy** — compare walk-forward vs settled tickets weekly
2. **Parlay quality** — Medium+ legs ≥68% model prob; block series-fade (lost last 2 vs opponent)
3. **Calibration** — High/Medium/Low hit rates vs claimed confidence
4. **Features** — head-to-head series (v2.2-h2h); ablate before shipping
5. **Strategy research (proactive — do not wait for user)**:
   - Run `python3 scripts/model/explore_all_strategies.py` at least weekly and after any ticket complaint
   - Read `public/strategy-explorer.json` — compare live plan vs top compound / hit rate / balanced at **shipped stakes**
   - Surface challengers that beat live on **both** hit rate and compound (or clearly dominate one with user tradeoff)
   - Test any leg count (2–4), med60 thresholds (58–65%), stake presets (flat + tiered)
   - **Do not** dismiss with "we already have the best" without running the explorer first
   - Ship strategy changes only after OOS review + user approval; document in `betting-plan.json`

Overnight loop: `scripts/model/run_overnight.sh` — research rotation every 15 min. **`explore_all_strategies.py` every 4th cycle.** Results: `public/strategy-explorer.json`, `data/overnight-research.jsonl`.

Report **both** compound backtest and flat $5 ROI. Flag when live rank drops in explorer.

## When to ask the user (only these)

- Push/deploy to production (main → Vercel)
- Strategy or stake rule changes
- API keys, billing (Odds API credits)
- Wallet balance update if unknown

Do **not** ask: whether to run today's ticket, whether to trust the model, whether to grade yesterday.

## Site

Production: `https://mlb-edge-woad.vercel.app` (not `mlb-edge.vercel.app`)
