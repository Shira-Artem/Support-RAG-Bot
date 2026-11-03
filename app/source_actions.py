"""Small shared vocabulary for source check and procedure boundaries."""
from __future__ import annotations

import re


CHECK_ACTION_TEXT = (
    r"проверьте|проверь|проверить|сверьте|сверь|сверить|"
    r"сопоставьте|сопоставь|сопоставить|посмотрите|посмотри|посмотреть|"
    r"убедитесь|убедись|убедиться|сравните|сравни|сравнить"
)
CHECK_ACTION_PATTERN = re.compile(r"\b(?:" + CHECK_ACTION_TEXT + r")\b", re.I)
CHECK_ACTION_ROOTS = ("провер", "свер", "сопостав", "посмотр", "убед", "сравн")

SOURCE_ACTION_TEXT = (
    CHECK_ACTION_TEXT +
    r"|откройте|открой|открыть|перейдите|перейди|перейти|зайдите|зайди|зайти|"
    r"нажмите|нажми|нажать|выберите|выбери|выбрать|напечатайте|напечатай|напечатать|"
    r"введите|введи|ввести|установите|установи|установить|"
    r"восстановите|восстанови|восстановить|передайте|передай|передать"
)
SOURCE_ACTION_PATTERN = re.compile(r"\b(?:" + SOURCE_ACTION_TEXT + r")\b", re.I)
