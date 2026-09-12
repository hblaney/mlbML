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

- **Strategy: `daily_force_top2`** — **2-leg ML parlay every day, never skip**
  - Official bet = model's **top two** moneylines by `pickProbability`
  - No High-gate. Thin 1-game slates fall back to a single.
  - Walk-forward: **leg hit ~66–68%** · **ticket hit ~43–45%** (parlay compounds)
- **Stakes:** **45%** two-leg · **35%** single fallback · **10%** three-leg
- **Honest KPIs:** `public/live-strategy-metrics.json`

Place one 2-leg every day. Regenerate with `generate_today_board.py` + `lock_daily_ticket.py`.

## When to ask the user

- Push/deploy to production, strategy or stake changes, API keys/billing, unknown wallet.
- Do **not** ask whether to run today's ticket or grade yesterday — just do it.
