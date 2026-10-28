# GitHub / source recovery — 28 октября 2026

## GitHub Actions: фактические доказательства

- [Runner Allocation #40753247435](https://github.com/PetrFedin/magadan/actions/runs/40753247435): **SUCCESS**, реальный назначенный runner и завершённый шаг.
- [Recovery Admission #40753247431](https://github.com/PetrFedin/magadan/actions/runs/40753247431): **Recovery tool / offline fixtures — SUCCESS**. Лог непосредственно подтверждает `Ran 42 tests in 0.387s` и `OK` на Python 3.13.17.
- Вторая стадия `SOURCE_ADMISSION_BLOCKED until real V7.9 sources exist`: **FAIL BY DESIGN**, поскольку оба требуемых независимых значения `HYDRO_TRUSTED_V79_ARCHIVE_SHA256` и `HYDRO_TRUSTED_V79_MANIFEST_SHA256` пусты, а полного дерева программы нет. `application-regression` не выполнена.
- Исторические сбои без runner (`runner_id=0`, `steps=[]`) датированы 27.10.2026; 28.10.2026 воспроизвести их не удалось. **Причина прежнего отказа runner неизвестна**. Не приписывать восстановление правкам Python.

## Состояние исходников

Библиотека содержит ZIP V7.9, ZIP V8 и V7.9 Git bundle, но попытка `files.materialize(raw_file)` возвращает `This Project file does not have an authorized raw-byte materialization path`. Официальная резервная копия в текущий контейнер не поступила. Подключённый MacBook-Air-Petr.local: OFFLINE.

Перенесены только отдельные **извлечённые исторические исследовательские документы** в `docs/archive_lab_references/`. Их присутствие не равнозначно импорту приложения и не подтверждает исторические тесты.

## Следующий допуск

1. Восстановить оригинальные байты V7.9/V8 на разрешённом носителе.
2. Отдельно засвидетельствовать SHA-256 оригинального архива и восстановленного манифеста.
3. Импортировать **полный код**, выполнить проверку на секреты и сравнение структуры.
4. Запустить CI Python/JS на конкретном SHA, затем отдельно PostgreSQL 17, RLS, backup/restore, OIDC/WORM, внешнюю инженерную сверку и предметный пилот с разрешениями собственника.

**Текущий итог: RUNNER PASS / RECOVERY TOOL 42 PASS / SOURCE IMPORT BLOCKED / APPLICATION CI NOT EXECUTED / PRODUCTION HOLD.**
