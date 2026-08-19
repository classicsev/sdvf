import os
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Optional

import httpx

# TLS-сертификат sandbox.alfabank.ru/baas.alfabank.ru выпущен НЕ цепочкой
# Альфы из архива банка (та — apica_2022_chain.cer — для другого, ей
# подписан только НАШ клиентский сертификат), а российским государственным
# Минцифры: Russian Trusted Root CA → Russian Trusted Sub CA (проверено
# напрямую через `openssl s_client -connect sandbox.alfabank.ru:443`).
# Этой пары нет в стандартном системном CA-бандле (certifi) — без явного
# verify=<этот файл> запрос падает с "self-signed certificate in certificate
# chain" ещё до какой-либо авторизации (найдено на реальном первом запросе,
# см. HANDOVER.md). Сами сертификаты публичные, не секрет.
_CA_CHAIN_PATH = str(Path(__file__).parent / "alfabank_ca_chain.pem")


class AlfaBankError(Exception):
    pass


@contextmanager
def _client_cert_files(cert_pem: str, key_pem: str):
    """mTLS требует файлы на диске — ssl.SSLContext.load_cert_chain() (через
    httpx) не умеет принимать PEM прямо из памяти. Пишем во временные файлы
    с правами только для владельца на время одного запроса и сразу удаляем."""
    cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
    key_fd, key_path = tempfile.mkstemp(suffix=".pem")
    try:
        os.fchmod(cert_fd, 0o600)
        os.fchmod(key_fd, 0o600)
        with os.fdopen(cert_fd, "w") as f:
            f.write(cert_pem)
        with os.fdopen(key_fd, "w") as f:
            f.write(key_pem)
        yield cert_path, key_path
    finally:
        os.unlink(cert_path)
        os.unlink(key_path)


class AlfaBankClient:
    """Клиент для Alfa API (Альфа-Банк), продукт «Выписки по счетам ЮЛ».

    См. https://developers.alfabank.ru/products/alfa-api/documentation/articles/transactions/articles/statement/v1/statement —
    GET /jp/v1/statement/transactions. В отличие от Т-Банка, statementDate —
    ОДНА конкретная дата (не диапазон "с — по"), поэтому за период приходится
    запрашивать каждый день отдельно; постранично внутри дня через page
    (не больше 1000 операций на страницу, останавливаемся на первой пустой
    странице). Транспорт — mTLS (сертификат+ключ) плюс заголовок
    Authorization: ApiKey {ключ}.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        cert_pem: str,
        key_pem: str,
        key_password: str,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.cert_pem = cert_pem
        self.key_pem = key_pem
        self.key_password = key_password
        self.timeout = timeout

    def fetch_statement_page(self, account_number: str, statement_date: date, page: int = 1) -> dict:
        headers = {"Authorization": f"ApiKey {self.api_key}", "Accept": "application/json"}
        params = {"accountNumber": account_number, "statementDate": statement_date.isoformat(), "page": page}
        with _client_cert_files(self.cert_pem, self.key_pem) as (cert_path, key_path):
            try:
                resp = httpx.get(
                    f"{self.base_url}/jp/v1/statement/transactions",
                    params=params,
                    headers=headers,
                    cert=(cert_path, key_path, self.key_password),
                    verify=_CA_CHAIN_PATH,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:
                raise AlfaBankError(f"Ошибка соединения с Alfa API: {exc}") from exc

        if resp.status_code != 200:
            raise AlfaBankError(f"Alfa API вернул {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def fetch_all_operations(self, account_number: str, date_from: date, date_to: Optional[date] = None) -> Iterator[dict]:
        end = date_to or date.today()
        day = date_from
        while day <= end:
            page = 1
            while True:
                data = self.fetch_statement_page(account_number, day, page=page)
                operations = data.get("transactions") or []
                for op in operations:
                    yield op
                if not operations:
                    break
                page += 1
            day += timedelta(days=1)


def _counterparty_name(op: dict, tx_type: str) -> Optional[str]:
    """Контрагент лежит в одном из трёх взаимоисключающих блоков в
    зависимости от валюты счёта/формата (rurTransfer/curTransfer/
    swiftTransfer — см. схему statement.yaml). При поступлении (income)
    деньги пришли ОТ плательщика (payer/orderingCustomer), при списании
    (expense) — ушли К получателю (payee/beneficiary)."""
    block = op.get("rurTransfer") or op.get("curTransfer") or op.get("swiftTransfer") or {}
    if tx_type == "income":
        return block.get("payerName") or block.get("orderingCustomerName")
    return block.get("payeeName") or block.get("beneficiaryCustomerName")


def map_operation(op: dict) -> Optional[dict]:
    """Переводит сырую операцию из выписки Alfa API в поля для Transaction —
    тот же контракт, что и у integrations/tbank.py::map_operation
    (external_ref/date_odds/type/amount/comment/counterparty_name/is_financing),
    используется одним и тем же import_mapped_transactions()."""
    operation_uuid = op.get("uuid")
    if not operation_uuid:
        return None

    direction = op.get("direction")
    if direction == "DEBIT":
        tx_type = "expense"
    elif direction == "CREDIT":
        tx_type = "income"
    else:
        return None

    raw_amount = (op.get("amount") or {}).get("amount")
    if not raw_amount:
        return None
    amount = Decimal(str(raw_amount))
    if amount <= 0:
        return None

    raw_date = op.get("operationDate") or op.get("documentDate")
    if not raw_date:
        return None
    try:
        date_odds = date.fromisoformat(raw_date[:10])
    except ValueError:
        return None

    return {
        "external_ref": f"alfa:{operation_uuid}",
        "date_odds": date_odds,
        "type": tx_type,
        "amount": amount,
        "comment": op.get("paymentPurpose") or None,
        "counterparty_name": _counterparty_name(op, tx_type),
        # Alfa API не размечает операции по кредитной линии отдельным кодом,
        # в отличие от Т-Банка (см. tbank.py::FINANCING_CATEGORIES) — нет
        # однозначного признака в схеме, чтобы определить это автоматически.
        "is_financing": False,
    }
