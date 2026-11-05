"""Credential boundary at input and output, independent of product knowledge."""
import re

SECRET_WARNING = ('Не присылайте токены, пароли и приватные ключи в чат или диагностические логи. '
                  'Для диагностики достаточно текста ошибки и статуса настройки без значения секрета.')
_CREDENTIAL = re.compile(r'токен\w*|парол\w*|секрет\w*|приватн\w*\s+ключ\w*|'
                         r'ключ\w*\s+доступ\w*|api[ _-]?(?:key|token)|private[ _-]?key|password|secret', re.I)
_SHARING = re.compile(r'присл\w*|присыл\w*|отправ\w*|переда\w*|высл\w*|высыл\w*|'
                      r'прикреп\w*|публиков\w*|публику\w*|сюда|\bвам\b|\bбот\w*|\bчат\w*|\bлог\w*', re.I)
_ASSIGNMENT = re.compile(
    r'((?:api[ _-]?(?:key|token)|access[ _-]?token|password|secret|токен|пароль|секрет)'
    r'\s*[:=]\s*[\"\']?)([^\s,;\"\']{6,})', re.I)
_SHAPED_SECRET = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?'
    r'-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
    r'\b(?:gsk_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|\d{6,}:[A-Za-z0-9_-]{20,})|'
    r'\bBearer\s+[^\s,;]+', re.I | re.S)


def redact_client_secrets(text: str) -> str:
    """Redact explicit credential assignments and recognizable key formats.

    Do not guess that release numbers, fiscal identifiers or ordinary words
    are secrets. Redaction occurs before provider requests and persistence.
    """
    text = _SHAPED_SECRET.sub('[REDACTED_SECRET]', text)
    return _ASSIGNMENT.sub(lambda m: m[1]+'[REDACTED_SECRET]', text)


def needs_secret_warning(text: str) -> bool:
    return bool('[REDACTED_SECRET]' in text or
                (_CREDENTIAL.search(text) and _SHARING.search(text)))


def with_secret_warning(answer: str, question: str) -> str:
    if needs_secret_warning(question) and SECRET_WARNING not in answer:
        return SECRET_WARNING+'\n\n'+answer
    return answer
