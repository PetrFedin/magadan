# Ступени независимой приёмки

| Рубеж | Статус | Критерий |
|---|---|---|
| Импорт исходников V7.9 | BLOCKED | Полное дерево исходников в одном SHA |
| GitHub CI | BLOCKED | Все проверки реально завершены на том же SHA |
| PostgreSQL 17 | BLOCKED | Нативные RLS, concurrent, restore, revoke tests |
| Corporate SSO/MFA | BLOCKED | Реальный IdP, отзыв доступа и изоляция ролей |
| External WORM audit | BLOCKED | Подписанные неизменяемые квитанции |
| Grid external reference | BLOCKED | Реальный независимый solver и согласованные допуски |
| Magadan field data | BLOCKED | Разрешения владельца и проверенные измерения |
| Real economics | BLOCKED | Подтверждённая смета, тарифная/налоговая методика |
| Construction M&V | BLOCKED | Действительные акты и нормализованная экономия |

Исторические сведения о 262 локальных Python и 63 JS тестах не являются GitHub CI. Переход к реальным средствам управления энергетикой не предусмотрен.
