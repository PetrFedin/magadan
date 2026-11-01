# HydroKontur 360 / Magadan V8.3 - source-verified monthly seasonality and local-day backtesting

2026-10-31 | DRAFT RESEARCH | based on V8.2 | PRODUCTION HOLD

## Authoritative published hydrology

Source: Rosvodresursy Order No 174, 07 July 2025, Section III, paragraph 11, table of characteristic intra-annual runoff for the Kolyma and Ust-Srednekan reservoir sections (88-year annual summary based on observations 1934-2021). This is an official legal/statistical source reproduced in ConsultantPlus; the underlying raw daily archive has NOT been obtained.
https://www.consultant.ru/document/cons_doc_LAW_511518/080fd801a8ed3e26f5c81964b6d1f06a42753b04/

Three selected historical water years are published for each gauging section:
- Wet characteristic 2004/05: upstream 23.00 km3 and downstream 39.27 km3.
- Average characteristic 2002/03: upstream 14.77 km3 and downstream 24.07 km3.
- Dry characteristic 1952/53: upstream 11.22 km3 and downstream 18.45 km3.
These names describe selected representative published examples, NOT the 5/50/95% regulatory quantiles, probabilistic model scenarios, current levels, or a sample of 88 annual records. A dry example year is not the historical minimum year.

The monthly source runs May-April, not January-December. Every monthly total reconciles EXACTLY with its published yearly total in this printed table (6/6). Derived warm-season May-September shares and cold-season October-April shares, from the 12 published monthly amounts:

| Section / selected water year | May-Sep (% of annual) | Oct-Apr (% of annual) | Highest-flow month |
| --- | ---: | ---: | --- |
| Kolyma upstream / wet 2004-05 | 96.09 | 3.91 | June |
| Kolyma upstream / average 2002-03 | 97.02 | 2.98 | June |
| Kolyma upstream / dry 1952-53 | 96.26 | 3.74 | June |
| Ust-Srednekan downstream / wet 2004-05 | 95.19 | 4.81 | June |
| Ust-Srednekan downstream / average 2002-03 | 95.93 | 4.07 | June |
| Ust-Srednekan downstream / dry 1952-53 | 95.56 | 4.44 | June |

Calculation: May-Sep percent = 100 * sum(monthly_km3[May..Sep]) / sum(monthly_km3[May..Apr]); Oct-Apr is the remaining sum. Rounding to two decimals (Decimal HALF_EVEN). All six selected profiles are severely seasonal; winter has only 2.98-4.81% across these examples. These percentages are DESCRIPTIVE OBSERVATIONS, not annual forecast distributions. Do not average over the three cases to generate a future forecast, assume they occur with equal probabilities, or add nested upstream/downstream annual water volumes.

The published selected years are protected by a local pinned SHA-256 over canonical JSON case values; this is integrity against later editing, NOT a signature issued by Rosvodresursy. Source code and original document link available under `data/references/V83_official_monthly_characteristic_years.json` and `server/hydro_api/hydro_monthly_v83.py`.

## Critical V8.2 bias fixed for the next research candidate

V8.2 used midnight UTC when selecting each historical forecast origin and used `as_of.date()` in UTC to determine the last complete observation. For a regional **daily mean** series whose day is defined in Magadan local time, midnight UTC is not the same instant as local midnight; observations released in the intervening hours could have been treated as known at an incorrect historical issuance time. This is a real potential as-of leakage and timezone/date boundary defect.

V8.3 adds an explicit *research-only* source contract: `reporting_timezone=Asia/Magadan`, `issue_local_hhmm=00:00`, `daily_series_basis=DAILY_MEAN_NATURAL_INFLOW`. It calculates local-day closure and historical issue time using IANA ZoneInfo and refuses records published before their local reporting day ends, records published after as_of, missing days, or measurements released too late for historical issue time. Neither the local midnight choice nor the source observation timezone has been verified with the real data owner; obtaining that agreement is an independent next gate, NOT a fact inferred from a CSV label.

This change runs on a **synthetic 1,095-day panel only**, for horizons 1/7/30 days, comparing two frozen naive benchmarks. It does not estimate current inflow, reservoir levels, daily MWh, dispatch instructions, or financial savings. Source and tests:
`server/hydro_api/hydro_backtest_v83.py` and `server/tests_v83/test_hydro_backtest_v83.py`.

Research-only output fields `forecast_for_2027`, `forecast_to_cascade`, `forecast_distribution`, `nested_gauge_total_km3` remain NULL, and every production/dispatch/investment flag remains false.

## Test receipt and blockers

Local environment Python 3.13.5: 48/48 source/scenario/unit tests PASS (23 published-source checks and 25 local-day historical-hindcast checks, both including invalid inputs). Tests use selected values transcribed from legal text plus synthetic gauge records. No real authorized daily series and no empirical prediction error on Kolym actuals.

A GitHub Actions workflow is committed for exact evidence gates, but hosted-runner GREEN is NOT certified. Earlier V8.2 run 41200913642 failed before executable steps; repository Actions policy/billing/runner root cause remains unknown.

Release sequence: source owner grant + original daily records and timezone mapping -> independent metrological review + vintage backtest -> signed hydro constraint map of both nested sections -> independently verified Cascade water balance and legal regime limits -> PostgreSQL17/RLS and identity E2E -> independent engineering/financial HydroCAPEX review. No SCADA/production changes.