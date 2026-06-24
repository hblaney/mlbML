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

- **Strategy: `parlay_first`** — parlay-heavy with quality gates:
  - Parlay legs: **≥ 65%** model prob · **≥ 8% edge** · **≥ 1 High/Elite leg**
  - No parlay → single only if **High/Elite ≥ 67%** and +EV; else **skip**
  - Model **High** tier requires **form edge ≥ 2%** (81.5% H/E walk-forward)
- **Stakes:** **45%** two-leg · **35%** elite single · **10%** three/four-leg
- **Honest KPIs:** `public/live-strategy-metrics.json` — flat ROI + ticket hit rate (not compound fantasy)

Walk-forward (Mar–Jun 2026, real closing odds): **81% ticket hit (13-3)**, **95% flat ROI**, **83% parlay hit** on 6 parlay days. Regenerate with `npm run model:daily:core`.

## When to ask the user

- Push/deploy to production, strategy or stake changes, API keys/billing, unknown wallet.
- Do **not** ask whether to run today's ticket or grade yesterday — just do it.
