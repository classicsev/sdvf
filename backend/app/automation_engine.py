import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AutomationRule, Counterparty
from app.schemas import TransactionCreate

_COMPARISON_OPS = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
}


def _field_value(field: str, payload: TransactionCreate, counterparty_name: Optional[str]):
    if field == "counterparty":
        return counterparty_name or ""
    if field == "comment":
        # Правило "комментарий содержит X" исторически ловило текст из банка
        # (раньше писался прямо в comment) — теперь он в отдельном
        # bank_payment_purpose (см. models.py), проверяем оба, чтобы уже
        # настроенные пользователем правила не сломались молча.
        purpose = getattr(payload, "bank_payment_purpose", None) or ""
        return f"{payload.comment or ''} {purpose}".strip()
    if field == "amount":
        return payload.amount
    if field == "category":
        return payload.category_id
    return None


def _condition_matches(condition: dict, payload: TransactionCreate, counterparty_name: Optional[str]) -> bool:
    field, op, value = condition.get("field"), condition.get("op"), condition.get("value")
    actual = _field_value(field, payload, counterparty_name)

    if op == "contains":
        return isinstance(actual, str) and str(value).lower() in actual.lower()
    if op == "equals":
        if isinstance(actual, str) or isinstance(value, str):
            return str(actual).lower() == str(value).lower()
        return actual == value
    if op == "not_set":
        return not actual
    if op in _COMPARISON_OPS:
        try:
            return _COMPARISON_OPS[op](float(actual), float(value))
        except (TypeError, ValueError):
            return False
    return False


def _rule_matches(rule: AutomationRule, payload: TransactionCreate, counterparty_name: Optional[str]) -> bool:
    conditions = rule.condition_json
    if isinstance(conditions, dict):
        conditions = [conditions]
    if not conditions:
        return False
    return all(_condition_matches(c, payload, counterparty_name) for c in conditions)


def apply_rules(db: Session, payload: TransactionCreate, company_id: str) -> dict:
    """Прогоняет активные правила автоматизации компании по новой операции и
    возвращает поля для переопределения (category_id/project_id). Срабатывает
    первое подошедшее правило — остальные не применяются."""
    counterparty_name = None
    if payload.counterparty_id:
        try:
            uuid.UUID(str(payload.counterparty_id))
        except (ValueError, AttributeError):
            counterparty = None
        else:
            counterparty = (
                db.query(Counterparty)
                .filter(Counterparty.id == payload.counterparty_id, Counterparty.company_id == company_id)
                .first()
            )
        counterparty_name = counterparty.name if counterparty else None

    rules = (
        db.query(AutomationRule)
        .filter(AutomationRule.company_id == company_id, AutomationRule.is_active.is_(True))
        .all()
    )
    for rule in rules:
        if _rule_matches(rule, payload, counterparty_name):
            action = rule.action_json or {}
            overrides = {}
            if action.get("set_category"):
                overrides["category_id"] = action["set_category"]
            if action.get("set_project"):
                overrides["project_id"] = action["set_project"]
            return overrides
    return {}
