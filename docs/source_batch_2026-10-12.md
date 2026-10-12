# Первая партия знаний по ККТ и ОФД — 12.10.2026

## Объём и границы

- В выбранных разделах обнаружено как минимум 39 потенциальных материалов: 28 обработанных HTML-статей и 11 ссылок на PDF-паспорта в каталоге Эвотора. Из 28 статей (13 из поддержки Эвотора и 15 из базы Платформы ОФД) подготовлено 30 самостоятельных Markdown-документов: 14 и 16 соответственно. Одна статья Эвотора разделена по моделям 6 и 7.3, одна таблица Платформы ОФД — по кодам ФЛК 507 и 508.
- Все 30 документов имеют `status: draft`, `collected_at: 2026-10-12`, исходный URL и заголовок. Модель указана лишь там, где её подтверждает источник; неизвестные версия и дата публикации оставлены пустыми. Разделы Markdown передаются в метаданные чанков.
- Конспекты написаны заново; полные тексты и изображения сторонних статей в репозиторий не переносились.
- Пилот составили три документа: ФН 235, связь Эвотора 6 с ОФД и передача чеков ККТ АТОЛ. После проверки загрузки и разбиения партия расширена.

## Источники и доступность

| Источник | Что исследовано | Результат |
| --- | --- | --- |
| [Поддержка Эвотора](https://support.evotor.ru/hc/ru) | Разделы ФН, ОФД, кассовых операций и моделей; открытые статьи ниже | 13 статей, 14 документов. [robots.txt](https://support.evotor.ru/robots.txt) при повторной проверке возвращал HTTP 500. Рассматривались только обычные публичные HTML-страницы, без обхода ограничений. |
| [Руководства Эвотора](https://evotor.ru/manuals/) | 11 ссылок на паспорта, в том числе для 5 line, 6, 7.2, 7.3, 10 и Power | 0 документов: все 11 ссылок ведут к PDF в `/static/`, а [robots.txt](https://evotor.ru/robots.txt) запрещает `/static/*.pdf`. PDF не загружались и их содержание не реконструировалось. |
| [База знаний Платформы ОФД](https://platformaofd.ru/baza-znaniy/) | Разделы ЛКК, ЛКП, ОФД/ККТ/ФН, контроля нарушений и другие вложенные страницы | 15 статей, 16 документов. [robots.txt](https://platformaofd.ru/robots.txt) доступен; статьи `/baza-znaniy/` не запрещены. Страницы с одним видео и нерелевантные сервисы не включались. |

Публичный сервер Qdrant на `127.0.0.1:6333` во время работы был недоступен: Docker Engine не запущен. Для проверки использован встроенный локальный Qdrant в игнорируемом каталоге `.local/qdrant_draft` и отдельная коллекция `knowledge_draft_sources_20261012`. Клиентская коллекция `knowledge_v1` не изменялась.

## Изученные и обработанные статьи

Каждая строка указывает исходную статью и созданный документ. Повторяющийся URL означает намеренное разделение по моделям или кодам, а не дубликат текста.

| Раздел | Исходная статья | Документ |
| --- | --- | --- |
| Эвотор, ФН | [235 / -3979](https://support.evotor.ru/article/360004715213) | `evotor/fn/fn-235.md` |
| Эвотор, ФН | [234](https://support.evotor.ru/article/360005580254) | `evotor/fn/fn-234.md` |
| Эвотор, ФН | [210 / -3910](https://support.evotor.ru/article/360004715693) | `evotor/fn/fn-210.md` |
| Эвотор, ФН | [212](https://support.evotor.ru/article/360016100393) | `evotor/fn/fn-212.md` |
| Эвотор, ФН | [217](https://support.evotor.ru/article/89e20cf4-b7e6-45a9-9a6c-6f1b7cc0a456) | `evotor/fn/fn-217.md` |
| Эвотор, ФН | [231 / -3975](https://support.evotor.ru/article/360005098974) | `evotor/fn/fn-231.md` |
| Эвотор, ОФД | [Диагностика связи](https://support.evotor.ru/article/360014099534) | `evotor/ofd/evotor-6-ofd-connection.md`, `evotor/ofd/evotor-7-3-ofd-connection.md` |
| Эвотор, ОФД | [Срок обслуживания](https://support.evotor.ru/article/8865646794770) | `evotor/ofd/ofd-subscription.md` |
| Эвотор, модели | [7.2](https://support.evotor.ru/article/360002718353) | `evotor/models/evotor-7-2.md` |
| Эвотор, модели | [7.3](https://support.evotor.ru/article/360002760513) | `evotor/models/evotor-7-3.md` |
| Эвотор, модели | [6 lite](https://support.evotor.ru/article/1d8e8869-2290-40f5-9a6a-1123b1877834) | `evotor/models/evotor-6-lite.md` |
| Эвотор, кассовые операции | [Смена на Эвоторе 6](https://support.evotor.ru/article/360006708093) | `evotor/cash/evotor-6-shift.md` |
| Эвотор, кассовые операции | [Копия документа на Эвоторе 6](https://support.evotor.ru/article/360005002514) | `evotor/cash/evotor-6-receipt-copy.md` |
| Платформа ОФД, АТОЛ | [Настройка ККТ АТОЛ](https://platformaofd.ru/baza-znaniy/nastrojka-kkt-atol/) | `platformaofd/atol/ofd-transmission-checks.md` |
| Платформа ОФД, Штрих-М | [Настройка ККТ Штрих](https://platformaofd.ru/baza-znaniy/nastroika-kkt-shtrih/) | `platformaofd/shtrih/ofd-connection-checks.md` |
| Платформа ОФД, кабинет | [Подключение ККТ](https://platformaofd.ru/baza-znaniy/podklyuchenie-kkt-k-lkk/) | `platformaofd/ofd/connect-kkt.md` |
| Платформа ОФД, кабинет | [Мониторинг касс](https://platformaofd.ru/baza-znaniy/lkk-razdel-kassy/) | `platformaofd/ofd/lkk-cash-monitoring.md` |
| Платформа ОФД, кабинет | [Поиск чеков](https://platformaofd.ru/baza-znaniy/lkk-razdel-cheki/) | `platformaofd/ofd/lkk-receipt-search.md` |
| Платформа ОФД, кабинет | [Покупка тарифа](https://platformaofd.ru/baza-znaniy/aktivacija-kkt-i-popolnenie-balansa-v-lk-klienta/) | `platformaofd/ofd/tariff-activation.md` |
| Платформа ОФД, кабинет | [Смена номера ФН](https://platformaofd.ru/baza-znaniy/smena-fn-v-lkk/) | `platformaofd/fn/fn-number-in-lkk.md` |
| Платформа ОФД, кабинет | [Архив ККТ](https://platformaofd.ru/baza-znaniy/archive-kkt/) | `platformaofd/ofd/archive-kkt.md` |
| Платформа ОФД, регистрация | [Перерегистрация ККТ](https://platformaofd.ru/baza-znaniy/pereregistraciya-kkt-v-fns/) | `platformaofd/fn/reregistration-kkt.md` |
| Платформа ОФД, регистрация | [Проверка статуса регистрации](https://platformaofd.ru/baza-znaniy/proverka-statusa-registracii-kkt/) | `platformaofd/fn/registration-status.md` |
| Платформа ОФД, регистрация | [Регистрация ККТ в ФНС](https://platformaofd.ru/baza-znaniy/registraciya-kkt-v-fns/) | `platformaofd/ofd/fns-registration.md` |
| Платформа ОФД, контроль | [Индикаторы ФНС](https://platformaofd.ru/baza-znaniy/kn-razdel-fns/) | `platformaofd/ofd/fns-indicators.md` |
| Платформа ОФД, контроль | [Индикаторы ЦРПТ](https://platformaofd.ru/baza-znaniy/kn-razdel-crpt/) | `platformaofd/marking/crpt-indicators.md` |
| Платформа ОФД, партнёры | [Кассы в ЛКП](https://platformaofd.ru/baza-znaniy/lkp-razdel-kassy/) | `platformaofd/ofd/partner-kkt-diagnostics.md` |
| Платформа ОФД, ФЛК | [Коды, не учитываемые в выручке](https://platformaofd.ru/baza-znaniy/kody-flk-ne-uchityvayushhiesya-v-vyruchke/) | `platformaofd/flk/flk-507.md`, `platformaofd/flk/flk-508.md` |

## Проверка качества

- `DocumentLoader` загрузил 30 документов: у всех уникальные хеши содержания, корректный URL, дата сбора и статус `draft`. `Chunker` создал 51 непустой чанк, максимальная длина — 791 символ при лимите 1200.
- Локальная тестовая коллекция содержит 51 точку. Повторная индексация сохранила прежние 20 документов без изменений и добавила 10 новых. Обычный `Retriever` с фильтром `approved` получил 0 результатов из этой коллекции.
- Запросы `ФН 235`, `ФН 234`, `ФЛК 507`, `ФЛК 508`, `Эвотор 7.2 питание`, `Эвотор 7.3 аккумулятор`, `Эвотор 6 lite ЕГАИС`, `АТОЛ не передаёт чеки`, `Штрих-М не передаёт чеки` нашли соответствующие документы. Запрос о незавершённой регистрации вывел нужную статью первым результатом. Посторонний запрос об астрономии дал 0 результатов.
- `python -m pytest -q`: 13 тестов пройдено. Отдельные проверки защищают точные коды, различение моделей, названного производителя и запрет индексировать черновики без отдельной коллекции.
- Повторный запуск штатного индексатора подтвердил идемпотентность: `python -m scripts.index_documents --docs-dir data/knowledge --draft-collection knowledge_draft_sources_20261012 --local-qdrant-path .local/qdrant_draft` вернул `indexed: 0`, `unchanged: 30`, `removed: 0`.

## Требуется проверка специалистом перед `approved`

1. Точность названий пунктов меню в текущих версиях ПО Эвотор 6, 6 lite, 7.2 и 7.3; версии прошивки в статьях не указаны.
2. Актуальные адрес, порт и ИНН Платформы ОФД перед практической настройкой конкретной ККТ.
3. Материалы о регистрации и перерегистрации ККТ, замене ФН и кодах ФЛК: сверить с текущими документами ФНС и фактическими реквизитами кассы. Черновики не предписывают выполнять фискальные изменения без специалиста.
4. Возможность законно получить паспорта и руководства из `evotor.ru/manuals/` и подготовить отдельные модельные конспекты. До этого версии и модели нельзя домысливать по оглавлению.

Ни один черновик не переводился в `approved`; `bot_crm` не менялся.
