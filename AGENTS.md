# MLB Edge — autonomous agent ops

You own this system. Treat the user's wallet (~$23) as real money. Do not wait to be asked.

## Every session (do first, no prompt needed)

1. **Read state**: `public/live-bankroll.json`, `public/predictions.json`, `public/betting-plan.json`
2. **Grade & refresh**: `python3 scripts/model/update_live_bankroll.py --wallet <current_wallet>`
3. **Report today's system ticket**: `corr_nl_reject_both`, model-pick-only, stakes 35/40/30
4. **Flag**: stale board (>2h), TBD/changed starters, missing odds, site vs local drift
5. **Fix blockers** before new features (broken deploy, wrong ticket logic, SSL/odds)

## Daily schedule (GitHub Actions — verify they ran)

| Time (CT) | Workflow | Purpose |
|-----------|----------|---------|
| ~5 AM | `daily-model.yml` | Retrain, full `model:daily`, commit outputs |
| ~12/4/7 PM | `refresh-board.yml` | Starters/odds refresh, live bankroll |

If board `generated_at` ≠ today → investigate Actions, run locally, push fix.

## Betting rules (canonical — never drift)

- **Strategy**: `corr_nl_reject_both`
- **Sides**: model predicted winner only (never +EV fade)
- **Stakes**: 35% single · 40% two-leg · 30% three-leg of **wallet_balance**
- **One ticket per day** — user does not add picks

## Model improvement loop (ongoing)

Priority order:

1. **Live accuracy** — compare walk-forward vs settled tickets weekly
2. **Parlay quality** — Medium+ legs ≥68% model prob; block series-fade (lost last 2 vs opponent)
3. **Calibration** — High/Medium/Low hit rates vs claimed confidence
4. **Features** — head-to-head series (v2.2-h2h); ablate before shipping
5. **Strategy** — only change after OOS test; document in `betting-plan.json`

Overnight loop: `scripts/model/run_overnight.sh` (board refresh, bankroll, sweep until 9 AM CT).

Do not chase backtest compound fantasy numbers. Optimize ticket hit rate and flat ROI at real stakes.

## When to ask the user (only these)

- Push/deploy to production (main → Vercel)
- Strategy or stake rule changes
- API keys, billing (Odds API credits)
- Wallet balance update if unknown

Do **not** ask: whether to run today's ticket, whether to trust the model, whether to grade yesterday.

## Site

Production: `https://mlb-edge-woad.vercel.app` (not `mlb-edge.vercel.app`)
