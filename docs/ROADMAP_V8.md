# V7.9 to V8 execution roadmap (sequenced by evidence gate)

## P0: repository and reproducibility

- [x] Assemble all locally available V7.9 source, schemas, specs and evidence into one navigable Git-ready working tree.
- [x] Introduce canonical entrypoint, release matrix, repository audit and one current CI workflow.
- [ ] Publish to verified target `magadan` GitHub repository via reviewed branch and inspect actual commit SHA.
- [ ] Confirm protected `main`, reviews, no bypass, required jobs and released tag.
- [ ] Run mandatory checks on one GitHub Actions SHA and store artifacts.

## P0: data security and benefit integrity

- [ ] Run migrations 001-140 in an isolated **real PG17** instance; prove RLS and transaction behavior with native suite.
- [ ] Implement consistent physical meter and cash-benefit boundary IDs across all modules and migrate legacy economic dossiers atomically.
- [ ] Add concurrency stress with multiple actors and tenant revocation, backups and restore.
- [ ] Connect approved corporate OIDC/MFA and external immutable audit receipt store; independently inspect keys/retention.

## P0: independent engineering pilot

- [ ] Obtain written Magadan owner approval and narrow 1 feeder reference boundary.
- [ ] Acquire schematics, dated topology, metering calibration, interval loads, real costs and legal permissions.
- [ ] Run independent externally validated powerflow with signed solver input/output and pre-agreed tolerances.
- [ ] Execute pre-registered before/after M&V: control for loads, weather, network changes and uncertainty.
- [ ] Sign field engineering report; no automated physical control.

## P1: six-domain expansion

- [ ] HydroForecast: calibrate physical hydrology on owner-approved basin, out-of-time quantile/backtest.
- [ ] CascadeEconomics: calibrate actual reservoir/routing/turbine constraints; independent safe scenario comparison.
- [ ] TurbineReliability: real condition labels, CMMS work order feedback, repair costs and false alert rates.
- [ ] HeatNet Economics: calibrated pressure/flow/thermal network; normalize weather and verify loss reduction.
- [ ] HydroCAPEX: linked WBS/CBS, procurement, permits, construction, M&V and independent actual-vs-plan budget.
- [ ] Portfolio: avoid double claiming one physical benefit across different organizations/assets, and separate mandated safety from optional NPV ranking.

## NO-GO criteria

No industrial launch, real investment return claim, regulator submission, grant claim, owner-referenced customer case or technology-control integration until respective proof and rights are collected. See `docs/V8_SIX_PRODUCTS_ENGINEERING_PLAN.md` for detailed domain acceptance.