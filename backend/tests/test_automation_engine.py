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


def test_single_condition_contains_matches(db_session):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb", "set_project": "proj-wb"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id))
    assert overrides == {"category_id": "cat-wb", "project_id": "proj-wb"}


def test_condition_does_not_match_returns_empty(db_session):
    cp = make_counterparty(db_session, "ООО Ромашка")
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id))
    assert overrides == {}


def test_compound_and_condition_requires_all_clauses(db_session):
    db_session.add(
        AutomationRule(
            condition_json=[
                {"field": "amount", "op": "lt", "value": 500},
                {"field": "comment", "op": "contains", "value": "комиссия"},
            ],
            action_json={"set_category": "cat-fee"},
        )
    )
    db_session.commit()

    # Сумма подходит, комментарий — нет
    overrides = apply_rules(db_session, _payload(amount=100, comment="обед"))
    assert overrides == {}

    # Оба условия подходят
    overrides = apply_rules(db_session, _payload(amount=100, comment="списана комиссия банка"))
    assert overrides == {"category_id": "cat-fee"}

    # Комментарий подходит, но сумма слишком большая
    overrides = apply_rules(db_session, _payload(amount=1000, comment="комиссия"))
    assert overrides == {}


def test_inactive_rule_is_not_applied(db_session):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "cat-wb"},
            is_active=False,
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id))
    assert overrides == {}


def test_first_matching_rule_wins(db_session):
    cp = make_counterparty(db_session, "ООО Вайлдберриз")
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "first"},
        )
    )
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "Вайлдберриз"},
            action_json={"set_category": "second"},
        )
    )
    db_session.commit()

    overrides = apply_rules(db_session, _payload(counterparty_id=cp.id))
    assert overrides["category_id"] == "first"


def test_amount_comparison_operators(db_session):
    db_session.add(
        AutomationRule(
            condition_json={"field": "amount", "op": "gte", "value": 1000},
            action_json={"set_category": "large"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(amount=999)) == {}
    assert apply_rules(db_session, _payload(amount=1000))["category_id"] == "large"
    assert apply_rules(db_session, _payload(amount=1500))["category_id"] == "large"


def test_not_set_operator_matches_empty_category(db_session):
    db_session.add(
        AutomationRule(
            condition_json={"field": "category", "op": "not_set", "value": None},
            action_json={"set_category": "fallback"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(category_id="")) == {"category_id": "fallback"}
    assert apply_rules(db_session, _payload(category_id="already-set")) == {}


def test_equals_operator_case_insensitive_string_match(db_session):
    cp = make_counterparty(db_session, "ООО Ромашка")
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "equals", "value": "ооо ромашка"},
            action_json={"set_category": "matched"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(counterparty_id=cp.id))["category_id"] == "matched"


def test_comparison_operator_with_non_numeric_value_does_not_crash(db_session):
    db_session.add(
        AutomationRule(
            condition_json={"field": "amount", "op": "gt", "value": "not-a-number"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload(amount=100)) == {}


def test_unknown_field_never_matches(db_session):
    db_session.add(
        AutomationRule(
            condition_json={"field": "does_not_exist", "op": "contains", "value": "x"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    assert apply_rules(db_session, _payload()) == {}


def test_empty_condition_list_never_matches(db_session):
    db_session.add(AutomationRule(condition_json=[], action_json={"set_category": "x"}))
    db_session.commit()

    assert apply_rules(db_session, _payload()) == {}


def test_malformed_counterparty_id_handled_gracefully(db_session):
    db_session.add(
        AutomationRule(
            condition_json={"field": "counterparty", "op": "contains", "value": "x"},
            action_json={"set_category": "x"},
        )
    )
    db_session.commit()

    # counterparty_id не проходит валидацию UUID — не должно уронить apply_rules
    overrides = apply_rules(db_session, _payload(counterparty_id="not-a-uuid"))
    assert overrides == {}


def test_rule_applied_end_to_end_on_transaction_create(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    account = make_account(db_session)
    fallback_category = make_category(db_session, "Прочее", TxTypeEnum.income)
    target_category = make_category(db_session, "Маркетплейсы", TxTypeEnum.income)
    cp = make_counterparty(db_session, "ООО Вайлдберриз")

    db_session.add(
        AutomationRule(
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
