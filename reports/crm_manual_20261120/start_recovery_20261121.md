# Pilot /start: команда принята, ответ редактируется выше текущего экрана

2026-11-21. После перезапуска владелец сообщил отсутствие ответа на четыре
`/start` и приложил screenshot. Проверка health/getUpdates сама по себе не
доказывает видимый ответ; прежнее сообщение о готовности стенда было недостаточно
проверено именно по нативному `/start`.

## Подтверждённая причина

Private trace сохранил четыре входящих `/start` 16:38:13–16:38:46 MSK. Каждый
попал в allowlisted pilot gate. Первый ответ выполнил успешный `editMessageText`
старого tracked menu; последующие три редактировали тот же ID и получили HTTP400
`message is not modified`. Это штатно трактуется safe-edit как успех, поэтому
fallback `sendMessage` не происходил. Старое меню находилось выше текущего вида
переписки, что согласуется со screenshot: последняя видимая поддержка вчера,
сегодня только команды пользователя. Поллер не зависал; allowlist, сеть,
RAG/model/KB не являются причиной данного случая.

Обычный registration `/start` уже вызывает существующий reset UI pointers.
Мой pilot gate перехватил эту команду раньше registration handler, но пропустил
reset и передал `show_main_menu` стандартное разрешение редактировать старый
screen. Следовательно, это ошибка pilot integration, а не отсутствие cleanup
механизма в CRM коллеги.

## Исправление

В существующем `bot/rag_pilot.py` `/start` повторяет существующий
`reset_tg_screen_history` (сохраняет профиль/верификацию), затем вызывает
`show_main_menu(force_send_new=True)`. `/menu` также требует нового видимого
screen, сохраняя существующее состояние reply keyboard. Поддержан `/start@bot`.
Нового menu/UI/регистрации не создавалось; safe-edit semantics и история CRM/RAG
не переписаны. Код outside pilot не менялся.

## Проверка

**44 passed**: pilot guard, UI reset и global navigation. Новая параметризованная
регрессия использует настоящий TelegramUIFlow с fake Telegram transport, старые
cached IDs и два последовательных вызова каждой команды. Подтверждает два
`send_message`, отсутствие `edit_message_text`, новый active pointer, сохранение
профиля и reset keyboard pointers для `/start`. Это offline доказательство
поведения, не выдаётся за Telegram LIVE.

Private before traces: CRM `.local/start-recovery-20261121/{events,http}-before.jsonl`;
test log `tests.txt`, финальный receipt `runtime-after.json` в той же директории.
Перед restart inflight0; перезапущены только CRM support и bot. API17808 сохранён;
новые support17044/poller7472, один polling worker,77/77 startup hashes обоих
CRM процессов совпадают, health/ready OK, getMe/getUpdates200.

## LIVE подтверждение после исправления

Владелец повторил `/start` 16:42:35 MSK. Трасса нового процесса подтверждает два
новых `sendMessage` HTTP200: persistent keyboard с пятью кнопками и новое
приветствие/меню. Старый screen не редактируется. Затем 16:42:41 владелец нажал
«💬 Чат»: карточка поддержки со ссылкой «Открыть чат на этом ПК» и существующими
контролами доставлена новым `sendMessage` HTTP200. Таким образом native pilot
link button принят Telegram; открытие браузера по ссылке ещё не наблюдалось.

Одновременно обнаружен отдельный cleanup defect: старое меню удаляется дважды
двумя best-effort задачами UIFlow (200, затем400 message to delete not found).
Это не ошибка отправки карточки и не причина молчания `/start`; оставлено как
отдельная cleanup проблема. Private after traces сохранены как
`events-after.jsonl`/`http-after.jsonl` в указанной директории.

Прочие quality/cleanup ограничения остаются открыты. Нового этапа, commit/push нет.
