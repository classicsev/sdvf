import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import DefaultDict, List, Optional, Tuple, TypedDict


class StatementParseError(Exception):
    pass


class ParsedTransaction(TypedDict):
    external_ref: str
    date_odds: date
    type: str  # "income" | "expense"
    amount: Decimal
    comment: Optional[str]
    counterparty_name: Optional[str]
    is_financing: bool


@dataclass
class ParsedStatement:
    bank: str
    account_number: Optional[str]
    period_from: Optional[date]
    period_to: Optional[date]
    # Остаток на начало/конец периода, если банк указывает его в самой справке/выписке
    # (Альфа-Банк и ВТБ — оба конца; Т-Банк — только "на дату формирования"; Сбер — нет).
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    closing_balance_date: Optional[date] = None
    transactions: List[ParsedTransaction] = field(default_factory=list)


class DedupKeyBuilder:
    """Строит external_ref для операций из PDF-выписок/справок, где нет родного id
    операции (в отличие от Т-Банк API, см. integrations/tbank.py). Ключ детерминирован
    (тот же файл при повторной загрузке даёт те же external_ref — дубли не создаются
    повторно), а порядковый номер добавляется только когда в пределах одной выписки
    встречаются операции с одинаковыми (дата, сумма, описание) — иначе они бы схлопнулись
    в один external_ref и "потеряли" бы друг друга при импорте.
    """

    def __init__(self, bank_tag: str, account_number: Optional[str]):
        self.bank_tag = bank_tag
        self.account_number = account_number or ""
        self._seen: DefaultDict[Tuple, int] = defaultdict(int)

    def build(self, d: date, amount: Decimal, description: str, extra: str = "") -> str:
        key = (d.isoformat(), str(amount), description, extra)
        seq = self._seen[key]
        self._seen[key] += 1
        raw = f"{self.account_number}|{d.isoformat()}|{amount}|{description}|{extra}|{seq}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        return f"statement:{self.bank_tag}:{digest}"
