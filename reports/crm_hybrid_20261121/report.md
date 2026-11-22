# Один бот: локальный checkpoint интеграции — 21.11.2026

Актуальная работа выполняется в существующих CRM/RAG integration checkout,
поверх прежних local deltas. Main app/KB не обновлялись и не сливались.
Причина молчания: case7 остался в queue после тестового вызова специалиста;
ИИ штатно заблокирован, реальный оператор в пилоте отключён.

Ограниченные исправления: явный возврат к ИИ в том же case, реальные состояния
attempts, отсутствие повторной истории/native replay, сохранение клиентских
реплик, одно уведомление о terminal API failure, один cleanup старого меню.
137 MySQL +2 HTTP-timeout/long PASS;422 units/2 прежних Windows failures.
LIVE RAG4.837s/accepted; mobile UI18messages/18unique. Native synthetic delivery
cancelled: не считать подтверждением доставки реальному клиенту.

[Полный отчёт, переходы, evidence и личный тест](C:/Users/Shira/.codex/worktrees/crm-rag-api/Rag/reports/crm_hybrid_20261121/report.md).

Следующий шаг — личный /chat → Вернуться к ИИ → Telegram/MiniApp/feedback/menu
replay. MAX/staff/remote HTTPS и полная native доставка длинных ответов не
приняты. Commit/push/production GO нет. Качество LLM/KB — после фундамента.
