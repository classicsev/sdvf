from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.auth import get_accessible_company_ids
from app.fx import convert_to_rub
from app.holding_transfers import detect_internal_transfer, get_or_create_internal_transfer_category
from app.models import Account, Category, Counterparty, Transaction, TxTypeEnum, User


def get_or_create_import_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    name = "Импорт из банка (приход)" if tx_type == "income" else "Импорт из банка (расход)"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(company_id=company_id, name=name, group_name="Импорт", type=tx_type)
        db.add(category)
        db.flush()
    return category


def get_or_create_financing_category(db: Session, tx_type: TxTypeEnum, company_id: str) -> Category:
    # Кредитная линия/овердрафт — не доход и не расход бизнеса (см.
    # integrations/tbank.py::FINANCING_CATEGORIES), отдельная категория с
    # is_financing=True, чтобы её можно было исключить из П&Л и дашборда,
    # не теряя сами операции из истории счёта.
    name = "Кредитная линия: пополнение" if tx_type == "income" else "Кредитная линия: погашение"
    category = db.query(Category).filter(Category.company_id == company_id, Category.name == name).first()
    if category is None:
        category = Category(
            company_id=company_id,
            name=name,
            group_name="Финансовая деятельность",
            type=tx_type,
            is_financing=True,
        )
        db.add(category)
        db.flush()
    return category


def get_or_create_counterparty(db: Session, name: str, company_id: str) -> Counterparty:
    counterparty = db.query(Counterparty).filter(Counterparty.company_id == company_id, Counterparty.name == name).first()
    if counterparty is None:
        counterparty = Counterparty(company_id=company_id, name=name)
        db.add(counterparty)
        db.flush()
    return counterparty


def import_mapped_transactions(
    db: Session,
    user: User,
    company_id: str,
    account: Account,
    mapped_ops: Iterable[Optional[dict]],
    dry_run: bool = False,
) -> dict:
    """Общий шаг импорта для любого источника, поставляющего операции в форме
    map_operation() из integrations/tbank.py (external_ref/date_odds/type/amount/
    comment/counterparty_name/is_financing) — используется как синком по API
    (routers/automation.py::_sync_bank_integration), так и разбором PDF-выписок/
    справок (statement_parsers/*, routers/statements.py) для банков без API у
    физлиц. Дедуп — по (company_id, external_ref), единый для обоих путей.

    dry_run=True считает created/skipped (дедуп и курс проверяются по-настоящему),
    но не создаёт категории/контрагентов и не пишет Transaction — для предпросмотра
    перед подтверждением импорта выписки.
    """
    created = 0
    skipped_duplicate = 0
    skipped_no_fx_rate = 0
    skipped_unparseable = 0
    # Холдинг = все компании/физлица, доступные пользователю, который делает импорт
    # (см. app/holding_transfers.py) — только среди них ищем "второй конец" перевода.
    holding_company_ids = get_accessible_company_ids(db, user)

    for mapped in mapped_ops:
        if mapped is None:
            skipped_unparseable += 1
            continue

        if (
            db.query(Transaction)
            .filter(Transaction.company_id == company_id, Transaction.external_ref == mapped["external_ref"])
            .first()
        ):
            skipped_duplicate += 1
            continue

        amount_rub = convert_to_rub(db, account.currency, mapped["amount"], mapped["date_odds"])
        if amount_rub is None:
            skipped_no_fx_rate += 1
            continue

        if dry_run:
            created += 1
            continue

        tx_type = TxTypeEnum(mapped["type"])
        if mapped.get("is_financing"):
            category = get_or_create_financing_category(db, tx_type, company_id)
        elif detect_internal_transfer(db, holding_company_ids, account.id, mapped.get("comment")):
            category = get_or_create_internal_transfer_category(db, tx_type, company_id)
        else:
            category = get_or_create_import_category(db, tx_type, company_id)
        counterparty_id = None
        if mapped.get("counterparty_name"):
            counterparty_id = get_or_create_counterparty(db, mapped["counterparty_name"], company_id).id

        db.add(
            Transaction(
                company_id=company_id,
                date_odds=mapped["date_odds"],
                account_id=account.id,
                category_id=category.id,
                counterparty_id=counterparty_id,
                type=tx_type,
                amount=mapped["amount"],
                currency=account.currency,
                amount_rub=amount_rub,
                comment=mapped["comment"],
                external_ref=mapped["external_ref"],
                created_by=user.id,
            )
        )
        created += 1

    skipped = skipped_duplicate + skipped_no_fx_rate + skipped_unparseable
    return {
        "created": created,
        "skipped": skipped,
        "skipped_duplicate": skipped_duplicate,
        "skipped_no_fx_rate": skipped_no_fx_rate,
        "skipped_unparseable": skipped_unparseable,
    }
