"""Versioned internal CRM contract. Client identity is an opaque case key."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RouteContext(StrictModel):
    channel: Literal['telegram', 'max', 'web', 'test']
    route: Literal['consultation', 'technical_support'] = 'consultation'
    router_version: str = Field(default='smart-navigation-v4', max_length=80)


class ReplyRequest(StrictModel):
    contract_version: Literal['1'] = '1'
    ticket_id: str = Field(pattern=r'^[A-Za-z0-9:_-]{1,120}$')
    message_id: str = Field(pattern=r'^[A-Za-z0-9:_-]{1,120}$')
    text: str = Field(min_length=1, max_length=8000)
    expected_revision: int = Field(ge=0, strict=True)
    context: RouteContext


class Source(StrictModel):
    id: str
    title: str | None = None


class ReplyResponse(StrictModel):
    contract_version: Literal['1'] = '1'
    ticket_id: str
    message_id: str
    revision: int
    reply_id: str
    answer: str
    status: Literal['answered', 'clarify', 'escalate', 'error']
    sources: list[Source] = Field(default_factory=list)
    escalation_reason: str | None = None
    diagnostics: dict[str, str | int | float | None] = Field(default_factory=dict)


class AckRequest(StrictModel):
    reply_id: str
    accepted: bool = True
