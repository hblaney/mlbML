# MLB Edge

Daily MLB predictions, best bets, stats, model accuracy, and approved stream embeds.

## What is included

- Home page with today's board
- Best Bets page with model edge and expected value
- Stats page for team-level model inputs
- Watch page for approved MLB Webcast iframe embeds
- Login page scaffold for Supabase Auth
- My Teams dashboard scaffold
- Public Accuracy page for daily/weekly/season performance
- Python model scripts for feature registry, backtesting, and daily retraining

## Algorithm

The model is now implemented in `scripts/model/`:

- **600+ pre-game features** from `feature_registry.py`
- **Rolling team form** from real MLB game results
- **Probable pitcher ERA** from the MLB Stats API
- **Ballpark context**: park factors, altitude, dimensions, dome status
- **Weather context**: temperature, wind, humidity, precipitation, pressure from Open-Meteo
- **Odds context**: moneyline, implied probability, totals, sportsbook source count through The Odds API
- **Elo ratings** updated after every game
- **HistGradientBoostingClassifier** blended with Elo (`35% Elo / 65% ML`)
- **Walk-forward backtesting** so the model only trains on games before the game it is predicting
- **Blind testing ledger** that locks predictions before games and grades them later

Run it:

```bash
pip3 install -r requirements.txt
python3 scripts/model/backtest.py
python3 scripts/model/train_daily.py
python3 scripts/model/blind_test.py predict
python3 scripts/model/blind_test.py grade
python3 scripts/model/data_audit.py
python3 scripts/model/feature_lab.py
```

For odds, set `ODDS_API_KEY` in `.env` or your shell. Without it, odds features fall back to neutral market priors.

Do **not** promote a model unless `data_audit.py` passes. It writes `public/data-audit.json` and blocks promotion when required real sources are missing, especially historical odds and Statcast.

## Feature selection

Use `scripts/model/feature_lab.py` before promoting model changes. It:

- ranks **every individual predictor** by correlation, mutual information, and univariate AUC
- writes the full per-feature score table to `all_feature_scores`
- tests top-N individual feature sets (`top_5`, `top_10`, `top_25`, etc.)
- evaluates feature groups with time-series cross validation
- runs group ablation tests to see what happens when each group is removed
- greedily combines groups only when validation accuracy improves
- writes the report to `public/feature-lab.json`

It intentionally does not brute-force every possible feature combination. With 899 predictors, that would be `2^899` combinations, which is not computationally realistic. The practical version is group screening, top-feature screening, and walk-forward validation.

Latest real backtest before adding odds/weather/park live feeds:

- **3,161 games evaluated**
- **56.2% overall accuracy**
- **99 days** at or above 60%
- **8 weeks** at or above 60%

That means the algorithm is real, but it is **not yet** hitting 60% overall. The public Accuracy page shows the honest record.

## Important note on accuracy

The site is built to **track and optimize** model accuracy. No honest model can guarantee 60% every day or week before it has proven historical results. The public Accuracy page is the right way to show whether the model is actually good.

## Local setup

```bash
cd mlb-edge
npm install
npm run dev
```

Open `http://localhost:3000`.

## Model scripts

```bash
python3 scripts/model/feature_registry.py
python3 scripts/model/backtest.py
python3 scripts/model/train_daily.py
python3 scripts/model/generate_today_board.py
python3 scripts/model/generate_prediction_history.py
python3 scripts/model/backtest_parlays.py
```

## Free deployment plan

- **Vercel**: frontend
- **Supabase**: login, favorite teams, stored predictions
- **GitHub Actions**: daily model run and backtest

The app is safe to deploy because hosted pages read generated JSON from `public/*.json`.
Local development can auto-run Python when data is stale, but Vercel does not run Python
from page renders.

Daily automation is defined in `.github/workflows/daily-model.yml`:

1. Pull yesterday's MLB results
2. Retrain through yesterday
3. Generate today's board with real odds when `ODDS_API_KEY` is available
4. Generate prediction history
5. Backtest parlay strategies
6. Commit updated `public/*.json`

### Deploy to Vercel

1. Push this folder to GitHub.
2. Import the GitHub repo into Vercel as a Next.js project.
3. Add the GitHub repository secret `ODDS_API_KEY`.
4. Add the Vercel environment variable `ODDS_API_KEY` too if you want manual
   Vercel rebuilds to have access to live odds.
5. The scheduled GitHub Action refreshes the public JSON every morning. Vercel
   redeploys when GitHub receives the commit.

To update the model later, edit files in `scripts/model/`, run:

```bash
npm run model:daily
npm run build
```

Then push to GitHub. The deployed website updates from the committed JSON outputs
and the next scheduled model run.

## Stream integration

Do not scrape hidden stream URLs. Ask MLB Webcast for approved embed URLs or a partner API, then store them in the `streamEmbeds` config or Supabase `streams` table.

## Next steps

1. Move your existing terminal predictor into `scripts/model/`
2. Connect Supabase Auth and favorite teams
3. Replace sample data in `lib/data.ts` with real schedule, odds, and prediction outputs
4. Add GitHub Actions for daily retraining
5. Get approved stream embed URLs from MLB Webcast
