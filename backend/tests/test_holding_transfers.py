from datetime import date
from decimal import Decimal

from app.holding_transfers import detect_internal_transfer, get_or_create_internal_transfer_category
from app.models import Company, CompanyMember, RoleEnum, Transaction, TxTypeEnum
from app.bank_import import import_mapped_transactions
from tests.conftest import auth_headers, make_account, make_category, make_company, make_user


def test_detect_internal_transfer_matches_account_number_in_comment(db_session):
    company_b = make_company(db_session, "Вторая компания холдинга")
    account_a = make_account(db_session, account_number="40817810000000000001")
    account_b = make_account(db_session, account_number="40817810000000000002", company_id=company_b.id)

    found = detect_internal_transfer(
        db_session,
        [account_a.company_id, company_b.id],
        account_a.id,
        f"Перевод на счёт {account_b.account_number} от Иванова",
    )
    assert found is True


def test_detect_internal_transfer_returns_false_without_match(db_session):
    account_a = make_account(db_session, account_number="40817810000000000001")
    found = detect_internal_transfer(
        db_session, [account_a.company_id], account_a.id, "Перевод на счёт 40817810099999999999"
    )
    assert found is False


def test_detect_internal_transfer_returns_false_without_comment(db_session):
    account_a = make_account(db_session, account_number="40817810000000000001")
    assert detect_internal_transfer(db_session, [account_a.company_id], account_a.id, None) is False
    assert detect_internal_transfer(db_session, [account_a.company_id], account_a.id, "") is False


def test_detect_internal_transfer_within_same_company_two_accounts(db_session):
    # Перевод между двумя своими же счетами ОДНОЙ компании — тоже перевод, не выручка.
    account_a = make_account(db_session, name="Счёт 1", account_number="40817810000000000001")
    account_b = make_account(db_session, name="Счёт 2", account_number="40817810000000000002")
    found = detect_internal_transfer(
        db_session, [account_a.company_id], account_a.id, f"Перевод на {account_b.account_number}"
    )
    assert found is True


def test_get_or_create_internal_transfer_category_is_idempotent(db_session):
    account = make_account(db_session)
    cat1 = get_or_create_internal_transfer_category(db_session, TxTypeEnum.income, account.company_id)
    cat2 = get_or_create_internal_transfer_category(db_session, TxTypeEnum.income, account.company_id)
    assert cat1.id == cat2.id
    assert cat1.is_internal_transfer is True


def test_list_categories_lazily_seeds_internal_transfer_categories(client, db_session):
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)

    resp = client.get("/categories", headers=headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Перевод между своими счетами: пополнение" in names
    assert "Перевод между своими счетами: списание" in names


def test_import_mapped_transactions_auto_routes_transfer_to_internal_category(db_session):
    company_b = make_company(db_session, "Вторая компания холдинга")
    account_a = make_account(db_session, name="Счёт А", account_number="40817810000000000001")
    account_b = make_account(db_session, name="Счёт Б", account_number="40817810000000000002", company_id=company_b.id)

    admin = make_user(db_session, RoleEnum.admin)
    db_session.add(CompanyMember(user_id=admin.id, company_id=company_b.id, role=RoleEnum.admin))
    db_session.commit()

    mapped_ops = [
        {
            "external_ref": "test:1",
            "date_odds": date(2026, 6, 1),
            "type": "expense",
            "amount": Decimal("1000.00"),
            "comment": f"Перевод на свой счёт {account_b.account_number}",
            "counterparty_name": None,
            "is_financing": False,
        },
        {
            "external_ref": "test:2",
            "date_odds": date(2026, 6, 2),
            "type": "expense",
            "amount": Decimal("500.00"),
            "comment": "Оплата поставщику ООО Ромашка",
            "counterparty_name": "ООО Ромашка",
            "is_financing": False,
        },
    ]

    result = import_mapped_transactions(db_session, admin, account_a.company_id, account_a, mapped_ops)
    db_session.commit()
    assert result["created"] == 2

    transfer_tx = db_session.query(Transaction).filter(Transaction.external_ref == "test:1").first()
    normal_tx = db_session.query(Transaction).filter(Transaction.external_ref == "test:2").first()
    assert transfer_tx.category.is_internal_transfer is True
    assert normal_tx.category.is_internal_transfer is False


def test_dashboard_summary_excludes_internal_transfer_from_income_expense(client, db_session):
    from datetime import date as _date

    today = _date.today().isoformat()

    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=1000)
    expense_cat = make_category(db_session, "Расход", TxTypeEnum.expense)
    transfer_cat = make_category(
        db_session, "Перевод между своими счетами: списание", TxTypeEnum.expense, is_internal_transfer=True
    )

    resp1 = client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": today,
            "account_id": account.id,
            "category_id": expense_cat.id,
            "type": "expense",
            "amount": 200,
            "currency": "RUB",
        },
    )
    assert resp1.status_code == 200
    resp2 = client.post(
        "/transactions",
        headers=headers,
        json={
            "date_odds": today,
            "account_id": account.id,
            "category_id": transfer_cat.id,
            "type": "expense",
            "amount": 300,
            "currency": "RUB",
        },
    )
    assert resp2.status_code == 200

    resp = client.get("/reports/dashboard-summary", headers=headers)
    body = resp.json()
    # В "Расход" должны попасть только 200 (обычная статья), 300 (перевод) исключены.
    assert body["period_expense_rub"] == 200.0
    # Но остаток счёта учитывает оба списания.
    acc = next(a for a in body["accounts"] if a["id"] == account.id)
    assert acc["balance"] == 1000 - 200 - 300
