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

- **Strategy: `power_parlay`** — parlay when a strong 2-leg ticket exists:
  - Both legs **High or Elite**
  - Each leg **>= 66%** model win probability
  - Best pair (not blind top-2) has **>= 52%** combined probability
  - If no parlay clears → **single** best High/Elite (never force weak parlays)
- **Stakes:** **50%** of wallet on 2-leg parlays · **20%** on singles (small bankroll tier)

Walk-forward validation (real closing odds, $10 compound): **67% ticket hit (40-20), $10→$182**, never below $10. **Parlay days: 9-4 (69%)** on 13 qualifying days. Do not revert to naive top-2 / calibrated_parlay (~53% coin flips).

## When to ask the user

- Push/deploy to production, strategy or stake changes, API keys/billing, unknown wallet.
- Do **not** ask whether to run today's ticket or grade yesterday — just do it.
