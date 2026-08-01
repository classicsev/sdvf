from datetime import date
from decimal import Decimal
from typing import Iterator, Optional

import httpx

SANDBOX_TOKEN = "TBankSandboxToken"


class TBankError(Exception):
    pass


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
        params = {"accountNumber": account_number, "from": date_from.isoformat(), "limit": limit}
        if date_to:
            params["to"] = date_to.isoformat()
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

    Имена полей payer/receiver не подтверждены по официальному openapi.yaml —
    перед первым реальным синком сверить с ответом песочницы/прод и поправить при расхождении.
    """
    operation_id = op.get("operationId")
    if not operation_id:
        return None

    credit = op.get("credit")
    debit = op.get("debit")
    if credit and Decimal(str(credit)) > 0:
        tx_type = "income"
        amount = Decimal(str(credit))
    elif debit:
        tx_type = "expense"
        amount = Decimal(str(debit))
    else:
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
    counterparty_name = (receiver.get("name") if tx_type == "expense" else payer.get("name")) or None

    return {
        "external_ref": f"tbank:{operation_id}",
        "date_odds": date_odds,
        "type": tx_type,
        "amount": amount,
        "comment": op.get("payPurpose") or op.get("description") or None,
        "counterparty_name": counterparty_name,
    }
