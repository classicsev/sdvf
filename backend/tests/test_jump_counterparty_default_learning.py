"""При ручной правке статьи/проекта у операции, сопоставленной с
Jump.Finance (jump_payment_id заполнен), выбор должен запоминаться на
контрагенте (Counterparty.default_category_id/default_project_id) — см.
routers/transactions.py::update_transaction и jump_matching.py."""

from decimal import Decimal

from app.models import Counterparty, RoleEnum, Transaction, TxTypeEnum
from tests.conftest import auth_headers, make_account, make_category, make_counterparty, make_project, make_user


def _make_jump_matched_tx(db_session, company_id, account, category, counterparty):
    tx = Transaction(
        company_id=company_id,
        date_odds="2026-06-01",
        account_id=account.id,
        category_id=category.id,
        counterparty_id=counterparty.id,
        type=TxTypeEnum.expense,
        amount=Decimal("5000"),
        currency="RUB",
        amount_rub=Decimal("5000"),
        external_ref="tbank:op-1",
        jump_payment_id="jump-1",
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


def test_manual_category_edit_on_jump_matched_tx_updates_counterparty_default(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    old_category = make_category(db_session)
    new_category = make_category(db_session, name="Услуги подрядчиков")
    project = make_project(db_session)
    counterparty = make_counterparty(db_session, name="Иванов Иван Иванович")
    tx = _make_jump_matched_tx(db_session, admin.company_id, account, old_category, counterparty)

    resp = client.patch(
        f"/transactions/{tx.id}",
        headers=headers,
        json={"category_id": new_category.id, "project_id": project.id},
    )
    assert resp.status_code == 200, resp.text

    db_session.refresh(counterparty)
    assert counterparty.default_category_id == new_category.id
    assert counterparty.default_project_id == project.id


def test_manual_edit_on_regular_tx_does_not_touch_counterparty_default(client, db_session):
    """Обычная (не сопоставленная с Jump) операция не должна учить контрагента —
    иначе любая ручная правка любой операции незаметно меняла бы дефолт."""
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)
    category = make_category(db_session)
    new_category = make_category(db_session, name="Другая статья")
    counterparty = make_counterparty(db_session, name="ООО Ромашка")
    tx = Transaction(
        company_id=admin.company_id,
        date_odds="2026-06-01",
        account_id=account.id,
        category_id=category.id,
        counterparty_id=counterparty.id,
        type=TxTypeEnum.expense,
        amount=Decimal("1000"),
        currency="RUB",
        amount_rub=Decimal("1000"),
    )
    db_session.add(tx)
    db_session.commit()

    resp = client.patch(f"/transactions/{tx.id}", headers=headers, json={"category_id": new_category.id})
    assert resp.status_code == 200, resp.text

    db_session.refresh(counterparty)
    assert counterparty.default_category_id is None
