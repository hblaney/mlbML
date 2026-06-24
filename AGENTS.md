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

- **Strategy: `strong_parlay`** — parlay ONLY when a genuinely strong 2-leg ticket exists:
  - Both legs **High or Elite**
  - Each leg **>= 67%** model win probability
  - Best available pair has **>= 52%** combined probability (different games)
  - If no parlay clears that bar → **single** best High/Elite pick (no forced weak parlays)
- **Stakes:** 45% of wallet on 2-leg parlays · 25% on singles (small bankroll tier)
- **Side:** always the model's predicted winner (never the +EV fade).
- **One bet per day.**

Walk-forward validation (real closing odds, $10 compound): **66.7% ticket hit (40-20), $10→$100, never dipped below $10**. Parlay days alone: **8-4 (66.7%)** on 12 qualifying days. The old naive top-2 / calibrated_parlay strategies were ~45-53% coin flips and caused the live losing streak — do not revert to those.

## When to ask the user

- Push/deploy to production, strategy or stake changes, API keys/billing, unknown wallet.
- Do **not** ask whether to run today's ticket or grade yesterday — just do it.
