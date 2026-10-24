# Расхождения прямого `claim_supported` с ручной разметкой

Положительный класс — `supported`; `general` исключён. Цитаты и ссылки на источник из исходной ручной разметки. Полный набор и второй gate — в `claim-decisions.csv`.

## False positive: неподтверждённое принято (30)

| ID | Ручная метка | Цитата | Ручной источник | Span неоднозначен |
|---|---|---|---|:---:|
| directbank/20b/2/04 | unsupported | Настройки → Конфигурация | — | нет |
| directbank/20b/2/05 | unsupported | Настройки → Банковские счета | — | да |
| directbank/20b/2/07 | unsupported | Банк → Банковские выписки | — | нет |
| directbank/20b/2/09 | unsupported | Настройки → Банковские счета → DirectBank | — | нет |
| directbank/20b/2/16 | unsupported | Банковские выписки» и «DirectBank | — | нет |
| directbank/20b/3/04 | unsupported | Настройки → Банковские счета | — | да |
| directbank/20b/3/06 | unsupported | Банк → Банковские выписки | — | нет |
| directbank/120b/2/07 | unsupported | Настройки взаимодействия с банком | — | нет |
| directbank/120b/2/08 | unsupported | Банковские счета организации | — | нет |
| directbank/120b/2/09 | unsupported | Включить обмен | — | да |
| directbank/120b/2/14 | unsupported | Загрузить выписку | — | да |
| directbank/120b/2/15 | unsupported | Загружать выписку по всем счетам | — | нет |
| directbank/120b/3/04 | unsupported | функция загрузки выписок сразу по всем счетам должна работать | — | нет |
| directbank/120b/3/08 | unsupported | Настройки обмена | — | да |
| directbank/120b/3/09 | unsupported | Включить обмен | — | да |
| directbank/120b/3/12 | unsupported | Журнал обмена | — | да |
| directbank/120b/3/15 | unsupported | Экспортировать настройки | — | нет |
| receipt_fd/20b/1/06 | unsupported | ФД из чека | — | нет |
| receipt_fd/20b/1/08 | unsupported | Платформа отобразит все чеки | — | нет |
| receipt_fd/20b/2/04 | unsupported | Дата начала | — | нет |
| receipt_fd/20b/2/05 | unsupported | Дата окончания | — | нет |
| receipt_fd/120b/2/06 | unsupported | **«С»** | — | нет |
| receipt_fd/120b/2/07 | unsupported | **«По»** | — | нет |
| aqsi_access/120b/2/14 | potentially_dangerous | после чего назначьте эту роль | — | нет |
| ofd_term/120b/2/04 | unsupported | сроке действия оплаченного тарифа | — | нет |
| ofd_term/120b/2/05 | unsupported | таблице «Кассы» | — | нет |
| ofd_term/120b/2/07 | unsupported | Дата активации | — | нет |
| ofd_term/120b/2/09 | unsupported | Срок действия до | — | нет |
| ofd_term/120b/2/16 | potentially_dangerous | необходимо либо активировать тариф | — | нет |
| ofd_term/120b/3/03 | unsupported | срок действия **оплаченного тарифа** | — | нет |

## False negative: подтверждённое отклонено (11)

| ID | Ручная метка | Цитата | Ручной источник | Span неоднозначен |
|---|---|---|---|:---:|
| receipt_fd/20b/2/03 | supported | первый и последний день | receipt:Поиск чеков | нет |
| receipt_fd/120b/1/03 | supported | номер ФД | receipt:Поиск чеков | да |
| receipt_fd/120b/2/03 | supported | первую и последнюю дату | receipt:Поиск чеков | нет |
| aqsi_access/20b/1/06 | supported | **«Сохранить»** | aqsi:Создать пользователя | нет |
| aqsi_access/20b/1/08 | supported | карточку редактирования | aqsi:Ограничения | нет |
| aqsi_access/20b/2/01 | supported | роли создаются заранее | aqsi:Создать пользователя | нет |
| aqsi_access/20b/2/02 | supported | уточните, есть ли уже роль | aqsi:Ограничения | нет |
| aqsi_access/20b/3/01 | supported | роли создаются заранее | aqsi:Создать пользователя | нет |
| aqsi_access/120b/1/04 | supported | одну из уже созданных ролей | aqsi:Создать пользователя | нет |
| aqsi_access/120b/1/05 | supported | **«Сохранить»** | aqsi:Создать пользователя | нет |
| ofd_term/120b/2/02 | supported | найдите нужную ККТ | tariff:Перед проверкой связи | нет |
