# HYDROKONTUR 360 — V8.2 acceptance record

**Date:** 2026-11-01. **Classification:** synthetic research; no actual Magadan water measurements. **Disposition:** `LAB PASS / BROWSER BLOCKED / PG NATIVE HOLD / FIELD HOLD / PRODUCTION HOLD`.

## Changed source

- `server/hydro_api/forecast_v82.py`: statistical one-to-seven-day daily-mean-flow engine with strict UTC data availability, selection/calibration/holdout, baseline, empirical intervals and descriptive risk flags.
- `server/hydro_api/forecast_api_v82.py` + `main.py`: authenticated stateless server route; tenant and synthetic asset checks, input/report/engine SHA-256.
- `server/ui/index.html`, `ui.js`, `ui.css`: dedicated research workspace, synthetic-generator, 28-point backtest plot, error KPI and risk explanation.
- `server/tests_v82`: regression, statistical leakage, API roles, integrity and UI wiring tests.
- `scripts/reproduce_v82.py`, `scripts/plot_forecast_v82.py`, `scripts/build_statistical_report_v82.py`: reproducible input, outputs and charts.
- `docs/V82_HYDROFORECAST_METHODS_RU.md`, `README_V82.md`: mathematical method, data model and field gate.
- `.github/workflows/native-v82.yml`: future GitHub runner check; its existence does not prove CI success.

## Executed local regression

| Suite | Test command | Result |
| --- | --- | --- |
| A: V7.1–V7.4 | `PYTHONPATH=server python -m pytest -q server/tests_v71 server/tests_v72 server/tests_v73 server/tests_v74 --ignore=server/tests_v71/test_postgres_native.py` | **132 PASS** |
| B: V7.5–V7.8 | `PYTHONPATH=server python -m pytest -q server/tests_v75 server/tests_v76 server/tests_v77 server/tests_v78 --ignore=server/tests_v78/test_postgres_native_v78.py` | **75 PASS** |
| C: V7.9–V8.2 + core | `PYTHONPATH=server python -m pytest -q server/tests_v79 server/tests_v8 server/tests_v81 server/tests_v82 server/tests --ignore=server/tests/test_browser.py` | **114 PASS, 1 SKIP** |
| JS | `cd v6-client && npm test` | **63 PASS** |
| Static JS | `node --check server/ui/ui.js` | **PASS** |
| Test cases / analysis | `PYTHONPATH=server python scripts/reproduce_v82.py` | **20/20 deterministic synthetic cases generated** |
| Charts | `PYTHONPATH=server python scripts/plot_forecast_v82.py` | Two static PNG figures generated |

Total **321 Python PASS, 1 SKIP, 63 JS PASS** across separately completed groups. Native PostgreSQL test modules V7.1 and V7.8 were explicitly excluded, V8.1 native test remains skipped. These numbers are **local**, not a confirmed GitHub Actions result for V8.2.

## Browser E2E attempted — blocked

`PYTHONPATH=server python scripts/browser_qa_v82.py` started a local FastAPI server and attempted Chromium login + forecast + visual checks at **1440/768/375**. Chromium returned:

`Page.goto: net::ERR_BLOCKED_BY_ADMINISTRATOR at http://127.0.0.1:<random>/lab`

This is an explicit **BROWSER E2E BLOCKED**, not a pass and not evidence of defects in the UI. The local API `TestClient` integration successfully exercised roles, cross-organization boundaries and prediction. No graphical browser acceptance is claimed.

## Synthetic statistical results (not field forecasts)

168 synthetic daily observations, evaluation horizon 2 days, nominal residual band 90%:

- Ordinary synthetic series: **MAE 6.361132 м³/с**, **RMSE 8.105325 м³/с**, holdout empirical coverage **23/28 = 82.142857%** (rounded output 0.821429), radius **12.252293 м³/с**, holdout lag-1 correlation **0.359506**.
- Injected +65 м³/с regime shift in final 28 days: **MAE 10.005494 м³/с**, **RMSE 17.394822 м³/с**, empirical coverage **21/28 = 75%**. MAE increased **57.291%** and RMSE increased **114.61%** by comparing the two model outputs; these are synthetic stress results, not environmental statistics.
- At horizon 7 days under +65 shift: **MAE 24.424385 м³/с** and empirical coverage **20/28 = 71.428571%**.
- Model selected for ordinary h=2: **persistence**, i.e. research model **did not beat** the trivial reference on the independent holdout. This is disclosed in API risk flags.
- Forecast target-day volume at h=2 ordinary case: **17.236761 million m³**, computed using `199.499552 м³/с × 86 400/10^6`, under a *single-day mean flow interpretation*. Not reservoir inflow or electricity generation.

Complete stress matrix with all 20 source SHA and metrics in `scenario_comparison_v82.json` / `.csv`, method in `docs/V82_HYDROFORECAST_METHODS_RU.md`.

## Rejection gates

1. Original input series contains only synthetic data, no hydropost verification, measured water volumes, snowpack and precipitation, operator records or approved reservoir transformation.
2. No reliable real-world probabilistic coverage, high-flow/flood calibration, field engineering sign-off, permitted asset data or forecasts from operational meteo-hydrological services.
3. No native PostgreSQL 17/RLS regression, OIDC/MFA, independent WORM receipts or validated browser E2E.
4. No recognized or realizable economic benefits, NPV, investment approval, dispatching or SCADA control.
5. This build remains an **integrated LAB candidate**. Do not merge or deploy to production until real release gates are met.

**Methodological references:** WMO Guidelines on the Verification of Hydrological Forecasts (WMO-No.1364, 2025), https://public.wmo.int/media/news/wmo-issues-guidelines-verification-of-hydrological-forecasts ; Oliveira et al. (2024), https://jmlr.org/beta/papers/v25/23-1553.html .
