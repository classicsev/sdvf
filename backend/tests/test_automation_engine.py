from app.automation_engine import apply_rules
from app.models import AutomationRule, RoleEnum, TxTypeEnum
from app.schemas import TransactionCreate
from tests.conftest import auth_headers, make_account, make_category, make_counterparty, make_user


def _payload(**overrides):
    base = dict(
        date_odds="2026-06-01",
        account_id="acc",
        category_id="cat",
        type="income",
        amount=100,
        currency="RUB",
    )
    base.update(overrides)
    return TransactionCreate(**base)


def test_single_condition_contains_matches(db_session, _default_company):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb", "set_project": "proj-wb"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id), _default_company.id)
    assert overrides == {"category_id": "cat-wb", "project_id": "proj-wb"}


def test_comment_condition_matches_bank_payment_purpose_too(db_session, _default_company):
    """Регрессия: назначение платежа из банка раньше писалось прямо в
    comment, теперь — в отдельном bank_payment_purpose (см. models.py).
    Правила "комментарий содержит X", настроенные ещё тогда, не должны
    молча переставать срабатывать."""
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "comment", "op": "contains", "value": "аренд"},
            action_json={"set_category": "cat-rent"},
        )
    )
    db_session.commit()

    overrides = apply_rules(
        db_session, _payload(comment=None, bank_payment_purpose="Оплата за аренду офиса"), _default_company.id
    )
    assert overrides == {"category_id": "cat-rent"}


def test_condition_does_not_match_returns_empty(db_session, _default_company):
    cp = make_counterparty(db_session, "ООО Ромашка")
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id), _default_company.id)
    assert overrides == {}


def test_compound_and_condition_requires_all_clauses(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json=[
                {"field": "amount", "op": "lt", "value": 500},
                {"field": "comment", "op": "contains", "value": "комиссия"},
            ],
            action_json={"set_category": "cat-fee"},
        )
    )
    db_session.commit()

    # Сумма подходит, комментарий — нет
    overrides = apply_rules(db_session, _payload(amount=100, comment="обед"), _default_company.id)
    assert overrides == {}

    # Оба условия подходят
    overrides = apply_rules(db_session, _payload(amount=100, comment="списана комиссия банка"), _default_company.id)
    assert overrides == {"category_id": "cat-fee"}

    # Комментарий подходит, но сумма слишком большая
    overrides = apply_rules(db_session, _payload(amount=1000, comment="комиссия"), _default_company.id)
    assert overrides == {}


def test_inactive_rule_is_not_applied(db_session, _default_company):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb"},
            is_active=False,
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id), _default_company.id)
    assert overrides == {}


def test_first_matching_rule_wins(db_session, _default_company):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "first"},
        )
    )
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "second"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id), _default_company.id)
    assert overrides["category_id"] == "first"


def test_amount_comparison_operators(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "amount", "op": "gte", "value": 1000},
            action_json={"set_category": "large"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(amount=999), _default_company.id) == {}
    assert apply_rules(db_session, _payload(amount=1000), _default_company.id)["category_id"] == "large"
    assert apply_rules(db_session, _payload(amount=1500), _default_company.id)["category_id"] == "large"


def test_not_set_operator_matches_empty_category(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "category", "op": "not_set", "value": None},
            action_json={"set_category": "fallback"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(category_id=""), _default_company.id) == {"category_id": "fallback"}
    assert apply_rules(db_session, _payload(category_id="already-set"), _default_company.id) == {}


def test_equals_operator_case_insensitive_string_match(db_session, _default_company):
    cp = make_counterparty(db_session, "ООО Ромашка")
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "equals", "value": "ооо ромашка"},
            action_json={"set_category": "matched"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(counterparty_id=cp.id), _default_company.id)["category_id"] == "matched"


def test_comparison_operator_with_non_numeric_value_does_not_crash(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "amount", "op": "gt", "value": "not-a-number"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(amount=100), _default_company.id) == {}


def test_unknown_field_never_matches(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "does_not_exist", "op": "contains", "value": "x"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(), _default_company.id) == {}


def test_empty_condition_list_never_matches(db_session, _default_company):
    db_session.add(
        AutomationRule(company_id=_default_company.id, condition_json=[], action_json={"set_category": "x"})
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(), _default_company.id) == {}


def test_malformed_counterparty_id_handled_gracefully(db_session, _default_company):
    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "x"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    # counterparty_id не проходит валидацию UUID — не должно уронить apply_rules
    overrides = apply_rules(db_session, _payload(counterparty_id="not-a-uuid"), _default_company.id)
    assert overrides == {}


def test_rule_applied_end_to_end_on_transaction_create(client, db_session, _default_company):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    fallback_category = make_category(db_session, "Прочее", TxTypeEnum.income)
    target_category = make_category(db_session, "Маркетплейсы", TxTypeEnum.income)
    cp = make_counterparty(db_session, "ООО Вайлдберриз")

    db_session.add(
        AutomationRule(
            company_id=_default_company.id,
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": target_category.id},
        )
    )
    db_session.commit()

    resp = client.post(
        "/transactions",
        headers=auth_headers(admin),
        json={
            "date_odds": "2026-06-01",
            "account_id": account.id,
            "category_id": fallback_category.id,
            "counterparty_id": cp.id,
            "type": "income",
            "amount": 1000,
            "currency": "RUB",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == target_category.id
