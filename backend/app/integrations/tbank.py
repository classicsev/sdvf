from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Iterator, Optional

import httpx

SANDBOX_TOKEN = "TBankSandboxToken"

# Служебные категории Т-Банк API (поле "category" в сыром ответе /api/v1/statement),
# относящиеся к работе кредитной линии/овердрафта, а не к операционной деятельности
# бизнеса — деньги реально движутся по счёту, но это не доход и не расход (см.
# routers/automation.py::_get_or_create_financing_category). Проверено на реальных
# данных: сумма incomeLoan и сумма creditPaymentOuter за период совпадали друг с
# другом и ровно на эту величину расходились "Приход/Расход" с веб-кабинетом банка
# (там такие операции не входят в счётчик "Списания и поступления").
FINANCING_CATEGORIES = {"incomeLoan", "creditPaymentOuter"}


class TBankError(Exception):
    pass


def _to_rfc3339(d: date, end_of_day: bool = False) -> str:
    # Т-Банк API требует полный date-time (RFC3339), голая дата "2022-01-01"
    # отклоняется как невалидный формат (проверено на реальном, не sandbox, API).
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(d, t, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class TBankClient:
    """Клиент для Т-Банк API (T-API), продукт «Операции по счету».

    См. https://developer.tbank.ru/docs/products/account-info —
    GET /api/v1/statement, пагинация через cursor/nextCursor.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def fetch_statement(
        self,
        account_number: str,
        date_from: date,
        date_to: Optional[date] = None,
        cursor: Optional[str] = None,
        limit: int = 1000,
    ) -> dict:
        params = {"accountNumber": account_number, "from": _to_rfc3339(date_from), "limit": limit}
        if date_to:
            params["to"] = _to_rfc3339(date_to, end_of_day=True)
        if cursor:
            params["cursor"] = cursor

        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v1/statement",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise TBankError(f"Ошибка соединения с Т-Банк API: {exc}") from exc

        if resp.status_code != 200:
            raise TBankError(f"Т-Банк API вернул {resp.status_code}: {resp.text[:300]}")

        return resp.json()

    def fetch_all_operations(
        self, account_number: str, date_from: date, date_to: Optional[date] = None
    ) -> Iterator[dict]:
        cursor = None
        while True:
            data = self.fetch_statement(account_number, date_from, date_to, cursor=cursor)
            # Точное имя поля со списком операций не задокументировано публично —
            # проверяем оба варианта, встречающихся в API Т-Банка.
            operations = data.get("operations") or data.get("data") or []
            for op in operations:
                yield op
            cursor = data.get("nextCursor")
            if not cursor:
                break


def map_operation(op: dict) -> Optional[dict]:
    """Переводит сырую операцию из выписки Т-Банка в поля для Transaction.

    Маппинг сверен с реальным (не sandbox) ответом /api/v1/statement: направление
    приходит в typeOfOperation ("Debit"/"Credit"), единого числового поля credit/debit
    в ответе нет — сумма всегда в accountAmount (в валюте счёта). Для карточных операций
    receiver почти всегда "АО «ТБанк»" (это банк-эквайер, не реальный получатель) —
    настоящий контрагент в таких случаях лежит в merch.name.
    """
    operation_id = op.get("operationId")
    if not operation_id:
        return None

    op_type = op.get("typeOfOperation")
    if op_type == "Debit":
        tx_type = "expense"
    elif op_type == "Credit":
        tx_type = "income"
    else:
        return None

    raw_amount = op.get("accountAmount") or op.get("operationAmount")
    if not raw_amount:
        return None
    amount = Decimal(str(raw_amount))
    if amount <= 0:
        return None

    raw_date = op.get("operationDate") or op.get("docDate") or op.get("trxnPostDate")
    if not raw_date:
        return None
    try:
        date_odds = date.fromisoformat(raw_date[:10])
    except ValueError:
        return None

    payer = op.get("payer") or {}
    receiver = op.get("receiver") or {}
    counter_party = op.get("counterParty") or {}
    merch = op.get("merch") or {}

    counterparty_name = (
        merch.get("name")
        or (payer.get("name") if tx_type == "income" else receiver.get("name"))
        or counter_party.get("name")
        or None
    )

    return {
        "external_ref": f"tbank:{operation_id}",
        "date_odds": date_odds,
        "type": tx_type,
        "amount": amount,
        "comment": op.get("payPurpose") or op.get("description") or None,
        "counterparty_name": counterparty_name,
        "is_financing": op.get("category") in FINANCING_CATEGORIES,
    }
