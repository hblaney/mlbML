# MLB Edge — agent ops (MANUAL MODE)

You own this system. Treat the user's wallet as real money.

**Automation is OFF.** All GitHub Actions workflows are `workflow_dispatch` only
(disabled 2026-06-24). Nothing retrains, refreshes, commits, or deploys on its own.
**You update the site by hand and push.** Do not re-enable schedules unless the user asks.

## How to update the site (do this when asked to "update the site")

Run from the `mlb-edge/` directory:

```bash
# 1. Regenerate today's board + all public outputs (board, history, accuracy,
#    CLV, health, strategy guard, consistency, and the locked daily ticket)
npm run model:daily:core

# 2. Verify the board is internally consistent (fails loudly if confidence/picks drift)
python3 scripts/model/prediction_integrity.py --full --strict-recompute

# 3. (optional) Grade yesterday's bet + update the live bankroll
python3 scripts/model/update_live_bankroll.py --wallet <current_wallet>

# 4. Commit + push — pushing to main is what deploys the site (Vercel auto-builds)
git add public/*.json data/locked-tickets/*.json data/live-bankroll-state.json
git commit -m "Update board for $(date +%F)"
git push origin main
```

- **Just the board, nothing else:** `npm run model:refresh-board`
- The live site only changes after you `git push origin main`. Refreshing Chrome does nothing on its own; Vercel redeploys ~2 min after the push.
- Production URL: `https://mlb-edge-woad.vercel.app`

## Betting strategy (canonical — keep `lib/data.ts` and `public/betting-plan.json` in sync)

- **Strategy: `quality_single`** — bet the single highest-ranked pick of the day,
  and **only fire when that pick is High or Elite confidence**. If the top pick is
  Medium/Low, it's a **no-bet day** (capital preservation).
- **Side:** always the model's predicted winner (never the +EV fade).
- **One bet per day.** The user does not add their own picks.
- Why singles, not parlays: on the walk-forward with real closing odds + $10 compound,
  the prior 2-leg parlay was a 52.9% coin-flip (37–33) that drew the bankroll down to
  $0.81 — the cause of the live losing streak. The High/Elite single hit 76.0% (38–12),
  grew $10→$91, and never dipped below the start.

## Open improvement for the next model (the user wants bigger upside)

Singles compound slowly ($10→$90/season is "nothing" to the user). The user wants
**parlays back** for real money. The honest path: parlay ONLY genuinely strong legs
(two Elite/High picks on days both exist). Not enough Elite-pair samples were available
to validate it yet. Before shipping any parlay mode:
1. Backtest 2-leg parlays built from **Elite/High legs only** on the walk-forward with
   real odds + compound bankroll (reuse `scripts/model/backtest_parlay2_compound.py`
   patterns; filter legs to `confidence in {Elite, High}`).
2. Require it to beat `quality_single` on **both** hit rate and ending bankroll, with a
   tolerable drawdown, before switching the live strategy.
3. Document the change in `public/betting-plan.json` and get user approval.

## When to ask the user

- Push/deploy to production, strategy or stake changes, API keys/billing, unknown wallet.
- Do **not** ask whether to run today's ticket or grade yesterday — just do it.
