# CHANGELOG

Проект переходит на [Semantic Versioning](https://semver.org/lang/ru/). Исторические метки Vx.y зафиксированы ниже как соответствие; новые релизы — только SemVer-теги (`v9.0.0`, `v9.1.0`, …) и GitHub Releases с манифестом SHA-256.

## Соответствие исторических версий

| SemVer | Историческая метка | Содержание | Статус доказательств |
|---|---|---|---|
| 8.0.0 | V8.0 | Восстановленные исходники 453/453, Boundary Graph, реестр эффектов | Локальный PASS (281 Python + 63 JS) |
| 8.1.0 | V8.1 | Колымская нормативная гидрология, атомарные границы, сериализация | Локальный PASS |
| 8.2.0 | V8.2 | HydroForecast: 3 benchmark-модели, rolling-origin, полоса ошибки | Локальный PASS |
| 8.3.0 | V8.3 | CascadeEconomics: двухступенчатый водный баланс, лаг, кривые | Локальный PASS |
| 8.3.1 | V8.3.1 | 438 почасовых проверок переноса, признание будущих допущений | Локальный PASS |
| 8.3.2 | V8.3.2 | Точный интеграл напора, rated-peak guard | Локальный PASS |
| 8.4.0 | V8.4 | CI, JUnit gate, exact SHA | — |
| 8.5.0 | V8.5 | Ролевые сессии engineer/auditor | — |
| 8.6.0 | V8.6 | Локальный PG17/Chromium, source-pinned runner | Hosted PASS (исторический SHA) |
| 8.7.0 | V8.7 | Единая PG17/OIDC/Chromium/recovery лаборатория | Hosted PASS (исторический SHA) |
| 8.8.0 | V8.8 | Региональный энергобаланс, условная NPV | Локальный PASS |
| 8.9.0–8.9.4 | V8.9.x | Provenance, карантин источников, Ed25519, hosted-CI evidence | Локальный PASS |
| 8.10.0 | V8.10 | Почасовая неидентифицируемость, 30 синтетических тестов | **Hosted PASS 16/19** (16.11.2026) |
| 8.11.0 | V8.11 | Issue #18: программа правомерных почасовых данных, N−1/LOLE | План |
| 9.0.0 | V9.0 | Open-science: NR power flow + бенчмарк pandapower IEEE 33-bus, Маскингам—Кундж, CRPS/PIT, ISO 20816 + Weibull MLE | Локальный PASS (32 теста) + внешний бенчмарк |
| 9.1.0 | V9.1 | Open-science II: опорные открытые параметры (data/reference), degree-day снеготаяние, LOLE/EENS адекватность, CRPS-декомпозиция Мёрфи—Hersbach, гидравлика и теплопотери теплосети | Локальный PASS (101 тест tests_v9) |

## [9.1.0] — 2026-11-16

### Добавлено
- `data/reference/kolyma_magadan_open_sources.json` + `data/reference/README.md` — опорные параметры из открытых опубликованных источников (класс `OPEN-PUBLISHED-REFERENCE`): каскад Колымских ГЭС (Колымская 900 МВт, Усть-Среднеканская 570 МВт), энергосистема Магаданской области (СО ЕЭС: установленная 1790 МВт, максимум нагрузки 460 МВт в 2023 г.), тарифы 2025-2026, климат Магадана (WMO 25913), гидрология Колымы (R-ArcticNET ст. 5858, рецензируемые статьи). Каждое число со `source_ref`; расхождения фиксируются, не усредняются
- `server/hydro_api/snowmelt_v9.py` — degree-day модель снегонакопления/снеготаяния (HBV/Hock): разделение фаз осадков, жидкая влага покрова, обратное замерзание, баланс воды с допуском 1e-9
- `server/hydro_api/adequacy_v9.py` — генерационная адекватность (issue #18): COPT рекуррентной свёрткой, LOLE/EENS по хронологической нагрузке, критерий N−1
- `server/hydro_api/crps_decomposition_v9.py` — точная декомпозиция CRPS на reliability/resolution/uncertainty (пороговая форма Hersbach 2000 + декомпозиция Мёрфи 1973); инвариант REL−RES+UNC == CRPS проверяется в рантайме с допуском 1e-9
- `server/hydro_api/heatnet_v9.py` — гидравлика Дарси—Вейсбах (Свами—Джейн, перекрёстная проверка Хааландом) и теплопотери изолированного участка; переходный режим 2300<Re<4000 помечается, не экстраполируется
- `server/tests_v9/` — 69 новых тестов (snowmelt 18, adequacy 21, crps_decomposition 12, heatnet 18); итого tests_v9: 101

### Изменено
- Зрелость HeatNet Economics: 1 → 2 (физика потерь и гидравлики, без натурной калибровки — HOLD сохраняется)

## [9.0.0] — 2026-11-16

### Добавлено
- `server/hydro_api/grid_powerflow_v9.py` — многоузловой AC Newton–Raphson для радиальных сетей; бенчмарк IEEE 33-bus против pandapower 3.5.6 (max |ΔV| = 4,8e-11 о.е.), скрипт `scripts/benchmark_grid_ieee33_v9.py`, квитанция `artifacts_v9/`
- `server/hydro_api/routing_v9.py` — русловая трансформация Маскингама—Кунджа, fail-closed на классической области коэффициентов
- `server/hydro_api/probabilistic_verification_v9.py` — CRPS, PIT, покрытие интервалов, rank histogram
- `server/hydro_api/turbine_reliability_v9.py` — зоны ISO 20816-5 (без зашитых границ), Weibull MLE с цензурированием (профильный метод), E[C] с принудительным HOLD
- `server/tests_v9/` — 32 теста; workflow `.github/workflows/v9-open-science.yml` подготовлен (файл в PR не включён: push workflow-файлов требует OAuth-scope `workflow`; добавляется владельцем)
- `docs/V9_OPEN_SCIENCE_MODULES_RU.md` — методология и верификация
- `docs/V9_OPEN_DATA_DOSSIER_RU.md` + `scripts/fetch_open_hydro_data.py` — досье открытых данных Колымы (R-ArcticNET/GRDC/GSIM/ArcticGRO/ERA5-Land) и скрипт скачивания с манифестом SHA-256

## [Unreleased]

### Добавлено
- docs/TECH_AUDIT_2026-11-16_RU.md — полный аудит и программа развития
- docs/INDEX.md — карта документации
- CHANGELOG.md, CITATION.cff

### Изменено
- README.md — единый канонический (версионные README остаются в корне как архив: на них ссылаются тесты)
- Консолидация: вся линия V8.1–V8.11 смержена в main (PR #20), цепочка Draft PR закрыта
- Репозиторий публичный; hosted CI восстановлен (issue #6)
