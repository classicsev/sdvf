import io
from datetime import date
from decimal import Decimal

from app.models import Account, RoleEnum, Transaction
from app.routers import statements as statements_router
from app.statement_parsers.base import ParsedStatement
from tests.conftest import auth_headers, make_account, make_user

FAKE_STATEMENT = ParsedStatement(
    bank="tbank",
    account_number="40817810000000000001",
    period_from=date(2026, 1, 1),
    period_to=date(2026, 3, 15),
    closing_balance=Decimal("9500.00"),
    closing_balance_date=date(2026, 3, 15),
    transactions=[
        {
            "external_ref": "statement:tbank_pdf:aaa",
            "date_odds": date(2026, 3, 10),
            "type": "expense",
            "amount": Decimal("500.00"),
            "comment": "Оплата в MAGAZIN",
            "counterparty_name": None,
            "is_financing": False,
        },
        {
            "external_ref": "statement:tbank_pdf:bbb",
            "date_odds": date(2026, 3, 5),
            "type": "income",
            "amount": Decimal("10000.00"),
            "comment": "Пополнение счета",
            "counterparty_name": None,
            "is_financing": False,
        },
    ],
)


def _upload(client, headers, account_id, dry_run=None):
    params = {} if dry_run is None else {"dry_run": dry_run}
    return client.post(
        f"/accounts/{account_id}/import-statement",
        headers=headers,
        params=params,
        files={"file": ("statement.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )


def test_dry_run_previews_without_writing_transactions(client, db_session, monkeypatch):
    monkeypatch.setattr(statements_router, "detect_and_parse", lambda data: FAKE_STATEMENT)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)

    resp = _upload(client, headers, account.id)  # dry_run по умолчанию True
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["created"] == 2
    assert body["skipped"] == 0
    assert body["bank"] == "tbank"
    assert body["closing_balance"] == "9500.00"
    assert len(body["preview"]) == 2

    assert db_session.query(Transaction).count() == 0


def test_commit_creates_transactions_and_dedupes_on_rerun(client, db_session, monkeypatch):
    monkeypatch.setattr(statements_router, "detect_and_parse", lambda data: FAKE_STATEMENT)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)

    resp = _upload(client, headers, account.id, dry_run=False)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is False
    assert body["created"] == 2
    assert body["preview"] == []
    assert db_session.query(Transaction).count() == 2

    # Повторная загрузка того же файла — дедуп по external_ref, ничего не дублируется.
    resp2 = _upload(client, headers, account.id, dry_run=False)
    body2 = resp2.json()
    assert body2["created"] == 0
    assert body2["skipped_duplicate"] == 2
    assert db_session.query(Transaction).count() == 2


def test_confirmed_import_reconciles_opening_balance_when_flow_does_not_match_statement(client, db_session, monkeypatch):
    # Реальный случай: остаток "на дату" из справки не обязан совпадать с
    # суммой (доход-расход) распарсенных операций один в один — на счету мог
    # быть остаток ещё ДО начала периода выписки. FAKE_STATEMENT: доход 10000,
    # расход 500, чистый поток +9500, но справка называет закрывающий остаток
    # 9600.00 — разница 100.00 должна лечь в opening_balance, а не потеряться.
    statement_with_gap = ParsedStatement(**{**FAKE_STATEMENT.__dict__, "closing_balance": Decimal("9600.00")})
    monkeypatch.setattr(statements_router, "detect_and_parse", lambda data: statement_with_gap)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=0)

    resp = _upload(client, headers, account.id, dry_run=False)
    assert resp.status_code == 200, resp.text

    db_session.refresh(account)
    assert account.opening_balance == Decimal("100.00")


def test_reimport_with_zero_new_operations_still_reconciles_balance(client, db_session, monkeypatch):
    # Ровно тот баг, который был найден на реальных данных пользователя: файл
    # уже когда-то загружали (все операции — дубли, created=0), но остаток
    # всё равно должен пересчитаться при повторной загрузке того же файла —
    # это единственный способ починить счёт без похода в базу руками.
    monkeypatch.setattr(statements_router, "detect_and_parse", lambda data: FAKE_STATEMENT)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session, opening_balance=0)

    resp1 = _upload(client, headers, account.id, dry_run=False)
    assert resp1.status_code == 200
    assert resp1.json()["created"] == 2

    # Кто-то (или баг) сломал остаток между первой и второй загрузкой.
    account = db_session.get(Account, account.id)
    account.opening_balance = Decimal("777.00")
    db_session.commit()

    resp2 = _upload(client, headers, account.id, dry_run=False)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["created"] == 0
    assert body2["skipped_duplicate"] == 2

    db_session.refresh(account)
    # opening_balance должен пересчитаться так, чтобы итоговый остаток снова
    # совпал с закрывающим остатком из справки (9500.00 = поток 10000-500),
    # а не остаться испорченным на 777.00.
    assert account.opening_balance + Decimal("10000.00") - Decimal("500.00") == Decimal("9500.00")


def test_non_admin_cannot_import_statement(client, db_session, monkeypatch):
    monkeypatch.setattr(statements_router, "detect_and_parse", lambda data: FAKE_STATEMENT)
    viewer = make_user(db_session, RoleEnum.viewer)
    headers = auth_headers(viewer)
    account = make_account(db_session)

    resp = _upload(client, headers, account.id)
    assert resp.status_code == 403


def test_parse_error_returns_400(client, db_session, monkeypatch):
    from app.statement_parsers.base import StatementParseError

    def _raise(data):
        raise StatementParseError("Не удалось распознать банк")

    monkeypatch.setattr(statements_router, "detect_and_parse", _raise)
    admin = make_user(db_session, RoleEnum.admin)
    headers = auth_headers(admin)
    account = make_account(db_session)

    resp = _upload(client, headers, account.id)
    assert resp.status_code == 400
