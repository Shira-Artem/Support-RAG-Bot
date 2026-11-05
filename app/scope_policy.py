"""Shared, typed scope compatibility for approved source evidence."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.dialogue_state import ENTITY_NAMES


HARDWARE_TASK_CATEGORIES = {
    "device", "fiscal_drive", "network", "network_diagnostics", "ofd_connection",
    "error_diagnosis", "receipt_transmission", "fiscal_document_control",
    "fiscal_format", "marking", "tspiot", "peripheral_setup",
}


def generic_physical_model(model: str | None, manufacturer: str | None) -> bool:
    """Recognize an explicit physical product class, never a model alias.

    The reviewed corpus also stores labels such as '<vendor> (physical KKT)'
    in the model field. Those labels constrain product family, not a numbered
    device. Unknown names, versions, and Online/cloud labels stay specific.
    """
    if not model or not manufacturer or re.search(r"\d|online|онлайн|cloud|облач", model, re.I):
        return False
    words = set(re.findall(r"[a-zа-яё]+", model.casefold()))
    brand = set(re.findall(r"[a-zа-яё]+", manufacturer.casefold()))
    rest = words - brand
    return (bool(brand) and brand <= words and bool(rest)
            and any(word.startswith("физическ") for word in rest)
            and all(word.startswith(("физическ", "касс", "терминал")) or word == "ккт"
                    for word in rest))


def matches_model_scope(model: str | None, equipment: str | None,
                        manufacturer: str | None = None) -> bool:
    """Compare a document's requirement with a client model, directionally."""
    if not model:
        return True  # No document model requirement; other scope gates still run.
    if generic_physical_model(model, manufacturer):
        if equipment and re.search(r"online|онлайн|cloud|облач", equipment, re.I):
            return False
        brand = manufacturer_from_equipment(equipment or "")
        return not brand or matches_scope_value(manufacturer or "", brand)
    if not equipment:
        return False
    required_numbers = re.findall(r"\d+(?:[.,]\d+)*", model)
    if required_numbers and required_numbers != re.findall(r"\d+(?:[.,]\d+)*", equipment):
        return False
    def designation(value):
        value = re.sub(r"[^a-zа-яё0-9]+", " ", value.casefold().replace("ё", "е")).strip()
        value = re.sub(r"^(?:(?:касса|ккт|терминал|модель)\s+)+", "", value)
        for slot, canonical, aliases in ENTITY_NAMES:
            if slot != "manufacturer":
                continue
            for alias in aliases:
                prefix = re.sub(r"[^a-zа-яё0-9]+", " ", alias.casefold()).strip()
                if value == prefix or value.startswith(prefix + " "):
                    return canonical.casefold() + value[len(prefix):]
        return value
    return designation(model) == designation(equipment)


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
    # A hardware model stays binding even if a neighboring category labels
    # the article as sales, catalog or another workflow. Software publishers
    # are not hardware brands and retain their separate service contract.
    hardware = hardware or bool(model and manufacturer_from_equipment(manufacturer))
    entities = state.task_entities
    # The legacy route facade deliberately hides non-route facts for cabinet
    # tasks. Hardware applicability still needs facts owned by the active
    # task, never the session's potentially stale equipment history.
    if hardware and state.operation != "explain" and state.task_context:
        entities = dict(entities)
        for slot in ("manufacturer", "equipment"):
            if slot in state.task_context.entities:
                entities[slot] = state.task_context.entities[slot]
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
    cloud_document = bool(service and ("облач" in model.casefold() or "cloud" in model.casefold()))
    cloud_service_scope = (
        (cloud_document or (bool(re.search(r"online|онлайн", model, re.I))
                            and matches_scope_value(service, model)))
        and any(matches_scope_value(service, value) for value in confirmed_service)
    )

    requirements: list[tuple[str, set[str]]] = []
    if service and not (manufacturer and matches_scope_value(service, manufacturer)):
        service_slots = {"service", "software", "integration", "ofd"}
        if scope.get("task_category") in HARDWARE_TASK_CATEGORIES:
            service_slots.add("manufacturer")
        requirements.append(("service", service_slots))
    if hardware and manufacturer and not (cloud_document or cloud_service_scope):
        requirements.append(("manufacturer", {"manufacturer"}))
    if hardware and model and not (cloud_document or cloud_service_scope) and not generic_physical_model(model, manufacturer):
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
        elif not any((matches_model_scope(expected, value, manufacturer) if field == "model"
                      else matches_scope_value(expected, value)) for value in values):
            mismatches.append(field)
    return ScopeAssessment(tuple(dict.fromkeys(missing)),
                           tuple(dict.fromkeys(mismatches)), cloud_service_scope)
