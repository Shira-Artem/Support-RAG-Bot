"""Shared, typed scope compatibility for approved source evidence."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.dialogue_state import ENTITY_NAMES


HARDWARE_TASK_CATEGORIES = {
    "device", "fiscal_drive", "network", "network_diagnostics", "ofd_connection",
    "error_diagnosis", "receipt_transmission", "fiscal_document_control",
    "fiscal_format", "marking", "tspiot",
}


def matches_scope_value(expected: str, confirmed: str) -> bool:
    """Match existing product aliases without collapsing Online and physical."""
    normalize = lambda value: re.sub(
        r"[^a-zа-я0-9]+", " ", str(value).casefold().replace("ё", "е")).strip()
    left, right = normalize(expected), normalize(confirmed)
    left_tokens, right_tokens = set(left.split()), set(right.split())
    if "онлайн" in left_tokens:
        left_tokens.remove("онлайн")
        left_tokens.add("online")
    if "онлайн" in right_tokens:
        right_tokens.remove("онлайн")
        right_tokens.add("online")
    if not left or not right:
        return False
    online = {"online", "онлайн"}
    if bool(left_tokens & online) != bool(right_tokens & online):
        return False
    return left_tokens <= right_tokens or right_tokens <= left_tokens


def manufacturer_from_equipment(value: str) -> str | None:
    """Resolve only an explicit, registered hardware brand or brand/model span.

    An arbitrary model name, a cloud service, and a substring of another
    product cannot establish a hardware manufacturer.
    """
    normalized = re.sub(r"\s+", " ", str(value).casefold().replace("ё", "е")).strip()
    known_services = [alias.casefold().replace("ё", "е")
                      for slot, _, aliases in ENTITY_NAMES if slot == "service" for alias in aliases]
    if any(normalized == service or normalized.startswith(service + " ")
           for service in known_services):
        return None
    matches = set()
    for slot, manufacturer, aliases in ENTITY_NAMES:
        if slot != "manufacturer":
            continue
        for alias in aliases:
            brand = alias.casefold().replace("ё", "е")
            if normalized == brand or re.fullmatch(
                    re.escape(brand) + r"\s+\d+(?:[.,]\d+)*[a-zа-я]?", normalized):
                matches.add(manufacturer)
    return next(iter(matches)) if len(matches) == 1 else None


@dataclass(frozen=True)
class ScopeAssessment:
    missing: tuple[str, ...] = ()
    mismatches: tuple[str, ...] = ()
    cloud_service_scope: bool = False


def assess_source_scope(state, scope: dict) -> ScopeAssessment:
    """Apply SourceFirst's customer-entity policy to source metadata.

    Manufacturer, service, software, integration, OFD, and equipment remain
    distinct confirmed slots. A manufacturer can satisfy a redundant vendor
    service label for hardware sources, but never a non-equivalent cloud
    service. Absence is reported separately from a confirmed conflict.
    """
    scope = scope or {}
    hardware = scope.get("task_category") in HARDWARE_TASK_CATEGORIES
    model = str(scope.get("model") or "")
    service = str(scope.get("service") or "")
    manufacturer = str(scope.get("manufacturer") or "")
    entities = state.task_entities
    confirmed_manufacturers = [fact.value for fact in entities.get("manufacturer", [])]
    # Equipment is a separate slot. It can establish only the manufacturer
    # explicitly encoded by an unambiguous known brand or brand/model mention.
    equipment_manufacturers = [brand for fact in entities.get("equipment", [])
                               if (brand := manufacturer_from_equipment(fact.value))]
    if confirmed_manufacturers and equipment_manufacturers and not any(
            matches_scope_value(left, right)
            for left in confirmed_manufacturers for right in equipment_manufacturers):
        return ScopeAssessment(mismatches=("manufacturer",))
    confirmed_service = [fact.value for fact in entities.get("service", [])]
    cloud_service_scope = (
        ("облач" in model.casefold() or "cloud" in model.casefold())
        and bool(service)
        and any(matches_scope_value(service, value) for value in confirmed_service)
    )

    requirements: list[tuple[str, set[str]]] = []
    if service and not (manufacturer and matches_scope_value(service, manufacturer)):
        service_slots = {"service", "software", "integration", "ofd"}
        if hardware:
            service_slots.add("manufacturer")
        requirements.append(("service", service_slots))
    if hardware and manufacturer and not cloud_service_scope:
        requirements.append(("manufacturer", {"manufacturer"}))
    if hardware and model and not cloud_service_scope:
        requirements.append(("model", {"equipment"}))

    missing: list[str] = []
    mismatches: list[str] = []
    for field, slots in requirements:
        expected = str(scope.get(field) or "")
        if not expected:
            continue
        values = [fact.value for slot in slots for fact in entities.get(slot, [])]
        if "manufacturer" in slots:
            values.extend(equipment_manufacturers)
        if not values:
            missing.append(field)
        elif not any(matches_scope_value(expected, value) for value in values):
            mismatches.append(field)
    return ScopeAssessment(tuple(dict.fromkeys(missing)),
                           tuple(dict.fromkeys(mismatches)), cloud_service_scope)
